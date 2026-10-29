# Security hardening — 28 October 2026

Scoped local application hardening, not production certification. SaaS-scale
testing remains on hold and scoring default-off. No tenant settings, credentials,
OS ACLs or provider consent changed. No new dependency or migration is needed.

## Implemented boundaries

### Monitoring

`GET /metrics` requires the existing current-session platform-admin gate.
Anonymous/invalid/ended sessions receive 401; organization admins and accounts
required to change their temporary password receive 403. Successful snapshots
are `Cache-Control: no-store`. `/health` and redacted `/ready` keep their existing
probe contracts. Counters remain per-process, not replica-wide aggregates.
External monitoring requires a separately designed noninteractive identity and
network policy: do not embed a human password or bypass authorization in a scraper.

### Before-body upload protection

| Transport | File limit | Whole-request limit |
|---|---|---|
| Asset/finding/profile import | `IMPORT_MAX_BYTES` (default 1 GiB) | File limit + 1 MiB |
| Organization/platform document | 10 MiB | 11 MiB |
| Organization logo | 2 MiB | 3 MiB |

Declared length and actual received bytes are checked **before multipart parsing/
spooling or route authentication**, including absent/underreported lengths and
trailing-slash redirects. Endpoints still enforce exact file limits. Metadata,
search and lifecycle routes are not uploads. Custom API prefixes are respected.
Oversized requests return 413 with CORS/security headers. This does not bound
request duration, concurrent transfers or total temporary-disk consumption.
An upstream proxy (including local Next rewrites) may buffer bytes before they
reach the API; ingress limits must therefore also protect that upstream hop.

29 October follow-up: browser metadata checks reject unsupported/oversized files
before content reads/submission. `GET /api/v1/upload-limits` (under the configured
API prefix) publishes only three non-sensitive byte ceilings, with `no-store`, no
database access and no settings writes. This lets imports use `IMPORT_MAX_BYTES`
instead of a guessed frontend constant. Fixed document/logo ceilings remain
10/2 MiB. Client checks are usability safeguards, not authorization or a substitute
for the transport/parser protections above; non-browser clients can bypass them.

`UPLOAD_RATE_LIMIT_PER_MINUTE=120` admits attempts per client address per API
process, across organizations/upload types. Invalid and unauthenticated attempts
count. Rejection occurs before body reads: 429 with `Retry-After`. A hard
10,000-address cap prevents unlimited bucket growth; at capacity new addresses
fail closed until stale buckets can be reclaimed. Live buckets are not evicted
to reset quotas. Sign-in retains its separate quota using the same bounded
implementation. No automatic resubmission/reimport is introduced.

These limits are **process-local**: restarts reset them; replicas do not share
them. NAT/proxy clients share an address quota, including the local Next forwarding
path's loopback bucket. The app uses the ASGI server's client address, never a raw
request's `X-Forwarded-For`. Restrict trusted proxies at the server and prevent
direct backend bypass. Distributed/gateway limits and per-tenant/concurrency
quotas remain necessary for multi-server SaaS.

### Temporary files and staged imports

Large imports now use exclusive, unpredictable standard-library temporary files
in `UPLOAD_DIR`: POSIX file mode 0600 and newly created leaf directory mode 0700.
Files close before worker rename; interrupted receives remove their owned file.
Existing/ancestor directory permissions are not rewritten. Windows permissions
still depend on inherited NTFS ACLs: POSIX modes are **not Windows ACL proof**.
With the current POSIX 0600 policy the API and worker must share the file-owner
identity; deployments with distinct identities need a deliberately tested shared
storage/ACL policy, not a root worker or world-readable files.

Checkpoint format v2 authenticates every state/chunk using HMAC-SHA256 and
constant-time comparison **before deserialization**. The MAC binds bytes to the
scan UUID, parser/settings fingerprint and state/chunk sequence. Unsigned,
tampered or substituted checkpoints cannot reach `pickle.loads`. Unreadable/old
state is discarded and the original file reread. A tampered publishing chunk
fails the import and rolls back publication, without partial assets/findings.
Existing resume and atomic publication semantics remain integration-tested.

API and workers must share `SECRET_KEY`. Rotation invalidates tokens and older
checkpoint signatures; incompatible state is reread, not trusted. Drain active
imports, stop old API/workers, then deploy/restart the same version/key together;
mixed-version worker rollout is not certified. Never expose signing of arbitrary
user-supplied serialized bytes. HMAC mitigates tampering; it does **not** make
pickle safe for arbitrary inputs or protect against application/key compromise.
It also does not prevent deletion/replay of valid checkpoints or replace database
access controls and availability protections.
A non-executable checkpoint format remains an option requiring representative
performance validation. See [Python's pickle guidance](https://docs.python.org/3/library/pickle.html).

## Static findings review

Bandit 1.9.4, `python -m bandit -r app -f json`. Artifacts:
`temp/testing/security-hardening-bandit-{before,after}.json` (ignored).
Before: **29 findings, 17 Medium / 12 Low / 0 High**. After centralized authenticated
deserialization: **28, 16 Medium / 12 Low / 0 High**. A count reduction alone is
not proof of safety. No `nosec`, path exclusions or severity-gate weakening was
added. Dispositions describe the inspected data flows, not future code changes.

| Rule / count after | Reviewed locations and disposition |
|---|---|
| B105 / 7 Low | `api/deps.py`, routes `events`, `people`, `platform`, `core/config.py`, `services/security_policy.py`: display/status labels and the deliberately rejected built-in key, not usable embedded credentials. Startup rejects default/short keys. |
| B110 / 3 Low | `core/observability.py` twice isolates failing alert callbacks; `services/readiness.py` returns redacted failed probes. Intentional error isolation, not an authorization bypass. Reliable external alert delivery remains a deployment gate. |
| B608 / 15 Medium | `archive_service.py` (11), `import_staging.py` (2), `platform.py` (1): fixed-code SQL fragments/table tuples, with record IDs bound. `db/evidence_revision.py` (1): dialect-quoted schema and fixed lifecycle names; trigger identifiers use PostgreSQL `%I`. No request-controlled SQL interpolation identified. Preserve these boundaries. |
| B403 + B301 / 1 Low + 1 Medium | `import_staging.py`: retained trusted-object serializer, now behind mandatory context-bound authentication. Not dismissed as a false positive; application/key trust remains as described above. |
| B405 / 1 Low | `nessus_parser.py`: stdlib `Element` type reference; actual parsing uses `defusedxml`, with XXE/entity-expansion regressions. No untrusted stdlib parser invocation identified. |

## Remaining deployment gates

- Shared/distributed login/request limits, tenant quotas, fair worker admission,
  ingress body/time/concurrency limits and resource monitoring.
- Private malware-scanner/quarantine policy: select the integration, timeout and
  failure behavior, then test it before production ingestion. Extension/content/
  parser validation and normalized logos are **not antivirus verdicts**. No file
  is sent to a third-party scanner in this increment. See the defense-in-depth
  recommendations in [OWASP's upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
- Actual service-account storage validation: upload/temp roots outside webroot;
  explicit API/worker read/write/traverse rights, no unrelated users or executable
  serving, capacity/retention and backup/restore checks. Windows needs owner and
  inherited/explicit NTFS grant inspection for the chosen identity; Linux needs
  ancestor ownership/modes and service umask checks. Readiness proves accessibility,
  not these policies. Do not recursively change workspace permissions.
- Secret-manager/rotation plan, least-privilege runtime versus migration DB roles,
  exact production CORS origins, HTTPS/secure cookies, explicit trusted proxies
  and backend network isolation.
- Production monitoring/export identity, external alert delivery and operational
  security review. Implementation `cd31793` passed its own hosted CI; future
  changes still require exact-SHA verification, not reuse of that result.

## Verification

From `backend`:

```text
python -m pytest --require-postgres -W error tests/unit/test_upload_hardening.py tests/unit/test_staging_integrity.py tests/unit/test_observability.py tests/unit/test_logo_transport.py tests/integration/test_security_hardening.py tests/integration/test_staged_import.py -q
```

Initial focused result: **72 passed in 17.42 s**. Includes real-session metrics
authorization, streamed/declared limits, no rejected-body reads, forwarded-header
spoof resistance, cross-upload quotas, threaded admission, bounded bucket growth,
file cleanup, authenticated resume, unsigned-state reread and atomic tampered-chunk
failure. Full/final results: [Phase 4 validation](PHASE4_VALIDATION.md).

Final regression: **1,409 full PostgreSQL tests** (778.01 s), **465 frontend
tests**, lint, **71 Chrome workflow checks + 17 correctness-only evidence-pilot
scenarios** pass. Both browser fixtures were removed; test public schema is
0031/35 tables with clean drift. No scale/load variant or real AI calls ran.
Implementation `cd317934e5d7611735022fddc21865fe19660da9` is reviewed, committed,
pushed and passed all four hosted Ubuntu jobs in
[run 40799748322](https://github.com/shalisarakkal/AuditMind/actions/runs/40799748322).
Authorized local activation then reused the existing frontend build, retaining
schema 0031, counts, credentials/configuration and zero enabled scoring settings.
Readiness and real pre-body 413/anonymous-metrics 401 checks pass, as does a fresh
Chrome 156 login/proxy smoke. No normal data upload/sign-in or provider call was
needed. [Detailed activation evidence](PHASE4_VALIDATION.md).

Fresh core/development and optional-embeddings manifest audits report **no known
vulnerabilities**; `pip check` reports no broken requirements. Audit reports:
`temp/testing/security-hardening-dependencies-{core,embeddings}.json`. No advisory
ignores or dependency changes were needed. These are point-in-time findings, not
a guarantee against undisclosed/future vulnerabilities. Fresh frontend npm audit
also reports **zero vulnerabilities**.
