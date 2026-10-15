"""Event logs as import sources (Phase 2f part 2): Azure Activity, AWS
CloudTrail, GCP Audit Logs and OSSEM endpoint events.

An event log records who did what and when, not assets, and a big one holds
hundreds of thousands of events. So each source's rules pick out the events
worth a look (a role assigned, a firewall opened, encoded PowerShell...) and
an EventTally sums each rule's matches up: how many, first and last seen,
who and where most often, a few examples. Once the whole file is read, each
rule with matches becomes one finding (per host, for an endpoint log that
names hosts): a few findings for a whole log, not one per event.

The tally is what a source's profile reads rows with (ProfileConfig.start):
a fresh one per import, saved with each staged chunk (snapshot/restore), so
it survives a resume. Everything it keeps is bounded, whatever the log: per
host groups (MAX_HOSTS), distinct values per group, each value's length,
and the examples' size.

Field names may be a column of a flat export or a dotted path into a nested
one ("userIdentity.arn"): both are looked up (see lookup()).
"""

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.models.enums import Domain, Severity
from app.services.import_staging import StagedRow

if TYPE_CHECKING:
    from app.services.import_profiles import ProfileConfig

# Kept per group: the most frequent actors and scopes listed, and examples.
TOP = 10
EXAMPLES = 5
# Distinct actors and scopes are counted exactly up to this many per group
# (fewer for a single host's); past it, "over 5,000", so a log of 500K
# different callers stays small.
DISTINCT_MAX = 5000
DISTINCT_MAX_PER_HOST = 50
# Hosts given a finding of their own per rule; events on further hosts go
# into one finding for "other hosts".
MAX_HOSTS = 500
# Characters kept of a value (an actor, a scope, a host), and checked by a
# rule's pattern.
VALUE_MAX = 300
MATCH_MAX = 8192
# An example event: nesting kept, characters per value, and its size in all.
EXAMPLE_DEPTH = 4
EXAMPLE_MAX = 1600
OTHER_HOSTS = "*"


@dataclass(frozen=True)
class Rule:
    key: str
    title: str
    domain: Domain
    severity: Severity
    matches: Callable[[dict], bool]
    # Fewer matching events than this in a group: no finding.
    min_events: int = 1


@dataclass(frozen=True)
class EventSource:
    """What an event family knows about its log: the fields that say when,
    who and where, and its rules."""

    time_field: str
    actor_field: str
    actor_noun: tuple[str, str]  # ("caller", "callers")
    scope_field: str | None
    scope_noun: tuple[str, str] | None  # ("subscription", "subscriptions")
    rules: tuple[Rule, ...]
    # An endpoint log that names hosts: one finding per rule per host, on
    # that host's asset.
    host_field: str | None = None


# --- Reading values -----------------------------------------------------------


def lookup(record: dict, name: str) -> Any:
    """A field's value: the record's column `name` (keys are lower case at
    the top level), else a dotted path into nested objects, matched without
    regard to case ("useridentity.arn" finds userIdentity -> arn)."""
    if name in record:
        return record[name]
    value: Any = record
    for part in name.split("."):
        if not isinstance(value, dict):
            return None
        if part in value:
            value = value[part]
            continue
        value = next((v for k, v in value.items() if isinstance(k, str) and k.lower() == part), None)
    return value


def text(value: Any) -> str:
    """A value as trimmed text; Azure wraps some as {"value": ...}."""
    if isinstance(value, dict):
        value = value.get("value", value.get("localizedValue"))
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _field_in(name: str, *values: str) -> Callable[[dict], bool]:
    """The field is one of `values` (without regard to case)."""
    wanted = {value.lower() for value in values}
    return lambda v: text(v.get(name)).lower() in wanted


def _matches(name: str, pattern: str) -> Callable[[dict], bool]:
    """The field contains `pattern` (a regex, without regard to case),
    looked for in its first MATCH_MAX characters: a pattern runs on every
    row, so a huge value can't make it slow."""
    compiled = re.compile(pattern, re.I)
    return lambda v: bool(compiled.search(text(v.get(name))[:MATCH_MAX]))


def _all(*tests: Callable[[dict], bool]) -> Callable[[dict], bool]:
    return lambda v: all(test(v) for test in tests)


def _not(test: Callable[[dict], bool]) -> Callable[[dict], bool]:
    return lambda v: not test(v)


# --- The tally -----------------------------------------------------------------


@dataclass
class _Capped:
    """Counts per value (each cut to VALUE_MAX characters), exact for the
    first `limit` distinct values; later new values only make it "more"."""

    limit: int = DISTINCT_MAX
    counts: Counter = field(default_factory=Counter)
    more: bool = False

    def add(self, value: str) -> None:
        if not value:
            return
        value = value[:VALUE_MAX]
        if value in self.counts or len(self.counts) < self.limit:
            self.counts[value] += 1
        else:
            self.more = True

    def single(self) -> str | None:
        """The one value, if there's exactly one."""
        return next(iter(self.counts)) if len(self.counts) == 1 and not self.more else None

    def distinct(self) -> str:
        return f"over {self.limit:,}" if self.more else f"{len(self.counts):,}"

    def digest(self) -> str:
        """Short, stable, whatever the order the values came in."""
        joined = "\n".join(sorted(self.counts)) + ("\n+" if self.more else "")
        return hashlib.sha256(joined.encode()).hexdigest()[:6]

    def top(self) -> list[dict]:
        return [{"value": value, "events": n} for value, n in self.counts.most_common(TOP)]


@dataclass
class _Group:
    row: int  # the first matching row, which the report names
    host: str | None  # as first seen (hosts are grouped without regard to case)
    events: int = 0
    first: datetime | None = None
    last: datetime | None = None
    actors: _Capped = field(default_factory=_Capped)
    scopes: _Capped = field(default_factory=_Capped)
    # Events on hosts past MAX_HOSTS, for the "other hosts" group.
    hosts: _Capped | None = None
    examples: list[dict] = field(default_factory=list)


class EventTally:
    """Reads an event log's rows into per-rule groups (see the module doc)."""

    def __init__(self, profile: "ProfileConfig"):
        self.profile = profile
        self.source: EventSource = profile.family.events
        self.groups: dict[tuple[str, str], _Group] = {}
        self.hosts_per_rule: Counter = Counter()
        # The rules in force, with their severity: the profile's settings over
        # the defaults.
        settings = profile.params.rules
        self.rules: dict[str, tuple[Rule, Severity]] = {}
        for rule in self.source.rules:
            setting = settings.get(rule.key)
            if setting is not None and not setting.enabled:
                continue
            self.rules[rule.key] = (rule, setting.severity if setting and setting.severity else rule.severity)

    # The profile interface (ingestion_service._RowChecker) --------------------

    @property
    def key(self) -> str:
        return self.profile.key

    @property
    def creates_assets(self) -> bool:
        return False

    @property
    def json_list_key(self) -> str:
        return self.profile.json_list_key

    def read_row(self, row: int, record: Any, ingestion, warnings: list[str]):
        """Tally one event; it gives nothing itself (finish() does)."""
        if not isinstance(record, dict):
            raise ValueError("record must be an object")
        values = self.profile.values(record)
        host = text(values.get(self.source.host_field))[:255] if self.source.host_field else ""
        when = None
        for rule, _ in self.rules.values():
            if not rule.matches(values):
                continue
            if when is None:
                when = _parse_time(text(values.get(self.source.time_field)))
            group = self._group(rule.key, host, row)
            group.events += 1
            if when is not None:
                group.first = when if group.first is None or when < group.first else group.first
                group.last = when if group.last is None or when > group.last else group.last
            group.actors.add(text(values.get(self.source.actor_field)))
            if self.source.scope_field:
                scope = text(values.get(self.source.scope_field))
                if self.source is AWS_CLOUDTRAIL and values.get("account"):
                    scope = f"{text(values['account'])}/{scope or 'global'}"
                group.scopes.add(scope)
            if group.hosts is not None:
                group.hosts.add(host.lower())  # hosts are told apart without regard to case
            if len(group.examples) < EXAMPLES:
                group.examples.append(_example(record))
        return None, []

    def finish(self) -> list[StagedRow]:
        """One finding per rule (and host) with enough matching events."""
        from app.services.ingestion_service import FindingRow  # imports this module

        staged = []
        for (rule_key, _), group in sorted(self.groups.items(), key=lambda item: item[1].row):
            rule, severity = self.rules[rule_key]
            if group.events < rule.min_events:
                continue
            details: dict = {
                "rule": rule.key,
                "actors": {"distinct": group.actors.distinct(), "top": group.actors.top()},
                "examples": group.examples,
            }
            if self.source.scope_noun:
                details["scopes"] = {
                    "name": self.source.scope_noun[1],
                    "distinct": group.scopes.distinct(),
                    "top": group.scopes.top(),
                }
            if group.hosts is not None:
                details["hosts"] = {"distinct": group.hosts.distinct(), "top": group.hosts.top()}
            finding = FindingRow(
                row=group.row,
                hostname=group.host,
                ip=None,
                domain=rule.domain,
                severity=severity,
                category=self._category(rule, group),
                description=self._describe(rule, group),
                source=self.profile.family.key,
                raw_data={},
                event_count=group.events,
                first_seen=group.first,
                last_seen=group.last,
                details=details,
            )
            staged.append(StagedRow(row=group.row, asset=None, findings=[finding]))
        return staged

    def snapshot(self) -> dict:
        return {"groups": self.groups, "hosts_per_rule": self.hosts_per_rule}

    def restore(self, state: dict) -> None:
        self.groups = state["groups"]
        self.hosts_per_rule = state["hosts_per_rule"]

    # --------------------------------------------------------------------------

    def _group(self, rule_key: str, host: str, row: int) -> _Group:
        """The rule's group for this host (or the whole log), made on first
        use; past MAX_HOSTS hosts for a rule, the "other hosts" group."""
        key = (rule_key, host.lower())
        group = self.groups.get(key)
        if group is not None:
            return group
        if host:
            if self.hosts_per_rule[rule_key] >= MAX_HOSTS:
                key = (rule_key, OTHER_HOSTS)
                group = self.groups.get(key)
                if group is None:
                    group = self.groups[key] = _Group(row=row, host=None, hosts=_Capped())
                return group
            self.hosts_per_rule[rule_key] += 1
        limit = DISTINCT_MAX_PER_HOST if host else DISTINCT_MAX
        group = self.groups[key] = _Group(row=row, host=host or None, actors=_Capped(limit), scopes=_Capped(limit))
        return group

    def _category(self, rule: Rule, group: _Group) -> str:
        """Title, where and when: what tells this finding from the same rule's
        in another log. One subscription (account, project...): named; more:
        their count and a short reference to which they are."""
        where = ""
        if group.hosts is not None:
            where = f" on other hosts [{group.hosts.digest()}]"
        elif self.source.scope_noun and group.scopes.counts:
            single = group.scopes.single()
            where = f" in {single}" if single else (
                f" in {group.scopes.distinct()} {self.source.scope_noun[1]} [{group.scopes.digest()}]"
            )
        when = f"{group.first:%Y-%m-%d} to {group.last:%Y-%m-%d}" if group.first and group.last else "no dates"
        suffix = f" ({when})"
        return f"{rule.title}{where}"[: 100 - len(suffix)] + suffix

    def _describe(self, rule: Rule, group: _Group) -> str:
        noun = "event" if group.events == 1 else "events"
        parts = [f"{rule.title}: {group.events:,} {noun}"]
        if group.actors.counts:
            parts.append(f" by {group.actors.distinct()} {_noun(self.source.actor_noun, group.actors)}")
        if self.source.scope_noun and group.scopes.counts:
            parts.append(f" in {group.scopes.distinct()} {_noun(self.source.scope_noun, group.scopes)}")
        if group.hosts is not None:
            parts.append(
                f" on {group.hosts.distinct()} more {_noun(('host', 'hosts'), group.hosts)} "
                f"(the first {MAX_HOSTS:,} each have their own finding)"
            )
        return "".join(parts) + "."


def _noun(noun: tuple[str, str], values: _Capped) -> str:
    return noun[0] if len(values.counts) == 1 and not values.more else noun[1]


def _example(record: dict) -> dict:
    """The event, trimmed: EXAMPLE_DEPTH levels, short keys and values, and
    at most EXAMPLE_MAX characters in all (else a cut-off text of it)."""

    def trim(value: Any, depth: int) -> Any:
        if isinstance(value, dict):
            if depth >= EXAMPLE_DEPTH:
                return "…"
            return {str(k)[:100]: trim(v, depth + 1) for k, v in list(value.items())[:30]}
        if isinstance(value, list):
            if depth >= EXAMPLE_DEPTH:
                return "…"
            return [trim(v, depth + 1) for v in value[:10]]
        if isinstance(value, str) and len(value) > VALUE_MAX:
            return value[:VALUE_MAX] + "…"
        return value

    example = trim(record, 0)
    rendered = json.dumps(example, default=str)
    return example if len(rendered) <= EXAMPLE_MAX else {"event": rendered[:EXAMPLE_MAX] + "…"}


def _parse_time(value: str) -> datetime | None:
    from app.services.import_profiles import parse_datetime  # imports this module

    return parse_datetime(value[:64]) if value else None


# --- The sources ---------------------------------------------------------------

AZURE_ACTIVITY = EventSource(
    time_field="time",
    actor_field="caller",
    actor_noun=("caller", "callers"),
    scope_field="subscription",
    scope_noun=("subscription", "subscriptions"),
    rules=(
        Rule("role_assignment_created", "Role assignment created", Domain.identity_access, Severity.high,
             _all(_matches("operation", r"roleassignments/write"), _field_in("status", "succeeded"))),
        Rule("role_assignment_failed", "Role assignment attempt failed", Domain.identity_access, Severity.medium,
             _all(_matches("operation", r"roleassignments/write"), _field_in("status", "failed"))),
        Rule("failed_operations", "Failed operations", Domain.identity_access, Severity.medium,
             _field_in("status", "failed"), min_events=10),
    ),
)

# A CloudTrail call that failed: an errorCode, or for a console sign-in an
# errorMessage and ConsoleLogin "Failure" (sign-ins have no errorCode).
_cloudtrail_ok = _all(_field_in("error", ""), _not(_field_in("console_result", "failure")))
_cloudtrail_root = _field_in("identity_type", "root")

AWS_CLOUDTRAIL = EventSource(
    time_field="time",
    actor_field="actor",
    actor_noun=("identity", "identities"),
    scope_field="region",
    scope_noun=("region", "regions"),
    rules=(
        Rule("root_console_sign_in", "Root account console sign-in", Domain.identity_access, Severity.critical,
             _all(_field_in("event_name", "ConsoleLogin"), _cloudtrail_root, _cloudtrail_ok)),
        Rule("root_activity", "Activity by the root account", Domain.identity_access, Severity.high,
             _all(_cloudtrail_root, _not(_field_in("event_name", "ConsoleLogin")), _cloudtrail_ok)),
        Rule("security_group_opened", "Security group opened", Domain.network_config, Severity.high,
             _all(_field_in("event_name", "AuthorizeSecurityGroupIngress"), _cloudtrail_ok)),
        Rule("bucket_policy_changed", "Bucket policy changed", Domain.compliance_alignment, Severity.medium,
             _all(_field_in("event_name", "PutBucketPolicy"), _cloudtrail_ok)),
        Rule("iam_user_created", "IAM user created", Domain.identity_access, Severity.medium,
             _all(_field_in("event_name", "CreateUser"), _cloudtrail_ok)),
        Rule("instances_terminated", "Instances terminated", Domain.backup_recovery, Severity.low,
             _all(_field_in("event_name", "TerminateInstances"), _cloudtrail_ok)),
    ),
)

# No status, OK, or code 0 (real logs give a numeric code; 7 is denied).
_gcp_ok = _field_in("status", "", "ok", "0")

GCP_AUDIT = EventSource(
    time_field="time",
    actor_field="principal",
    actor_noun=("principal", "principals"),
    scope_field="project",
    scope_noun=("project", "projects"),
    rules=(
        Rule("firewall_changed", "Firewall rule changed", Domain.network_config, Severity.high,
             _all(_matches("method", r"compute\.firewalls\.(patch|insert|update|delete)"), _gcp_ok)),
        Rule("service_account_created", "Service account created", Domain.identity_access, Severity.medium,
             _all(_matches("method", r"serviceaccounts\.create|CreateServiceAccount$"), _gcp_ok)),
        Rule("bucket_updated", "Storage bucket updated", Domain.compliance_alignment, Severity.medium,
             _all(_matches("method", r"storage\.buckets\.(update|patch)|storage\.setIamPermissions"), _gcp_ok)),
        Rule("permission_denied", "Permission denied", Domain.identity_access, Severity.medium,
             _field_in("status", "permission_denied", "7")),
    ),
)

OSSEM_EVENTS = EventSource(
    time_field="time",
    actor_field="user",
    actor_noun=("user", "users"),
    scope_field=None,
    scope_noun=None,
    host_field="host",
    rules=(
        Rule("encoded_powershell", "Encoded PowerShell command", Domain.incident_response, Severity.critical,
             _matches("command_line", r"powershell(\.exe)?\b.{0,2000}?\s-(e|ec|enc|encodedcommand)\b")),
        Rule("run_key_persistence", "Run key persistence", Domain.incident_response, Severity.high,
             _matches("registry_key", r"\\CurrentVersion\\Run(Once)?\b")),
        Rule("dll_in_temp", "DLL written to a Temp folder", Domain.incident_response, Severity.high,
             _matches("file_path", r"\\Temp\\[^\\]*\.dll$")),
        Rule("new_service", "Service registry key set", Domain.incident_response, Severity.medium,
             _matches("registry_key", r"\\CurrentControlSet\\Services\b")),
        Rule("whoami_reconnaissance", "whoami reconnaissance", Domain.incident_response, Severity.medium,
             _matches("command_line", r"\bwhoami(\.exe)?\b")),
    ),
)
