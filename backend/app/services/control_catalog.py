"""Pinned local catalog installation; append-only tenant mapping decisions."""
import hashlib
import json
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select, text, tuple_
from sqlalchemy.exc import DBAPIError

from app.api.deps import authorize_org_write
from app.models.control_catalog import ControlCatalog, CatalogControl, FindingControlRule, FindingControlDecision, FindingControlTarget
from app.models.finding import Finding
from app.models.enums import UserRole
from app.models.user import User
from app.services.events import record_event
from app.services.knowledge_standards import NIST_SOURCE
from app.schemas.control_catalog import ControlMappingSummary

NIST_HASH = "4836943f21d393f2821df85ada4e6f3c0617243b4ddf44263fe68205400210b4"
NIST_RIGHTS = "US government public domain / CC0 1.0; no NIST endorsement implied."


def baseline():
    raw = (Path(__file__).resolve().parents[1] / "data" / "nist_csf_2_catalog.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != NIST_HASH:
        raise HTTPException(409, "Bundled catalog differs from the verified source; installation refused")
    catalog = json.loads(raw)["catalog"]
    controls = []

    def walk(node, category=""):
        if node.get("class") == "category":
            category = node["title"]
        withdrawn = any(p.get("name") == "status" and p.get("value") == "withdrawn" for p in node.get("props", []))
        if node.get("class") == "subcategory" and not withdrawn:
            reference = node["id"]
            description = "\n\n".join(p["prose"] for p in node.get("parts", []) if p.get("name") == "statement" and p.get("prose"))
            if not description:
                raise HTTPException(409, "Verified catalog outcome has no statement")
            controls.append(dict(control_id=uuid.uuid5(uuid.NAMESPACE_URL, "urn:auditmind:control:nist-csf:" + reference),
                reference=reference, title=f"{reference}: {category}", description=description))
        for key in ("groups", "controls"):
            for child in node.get(key, []):
                walk(child, category)

    walk(catalog)
    if len(controls) != 106 or len({c["control_id"] for c in controls}) != 106:
        raise HTTPException(409, "Verified catalog outcome set is incomplete")
    return dict(id=uuid.uuid5(uuid.NAMESPACE_URL, NIST_SOURCE + "#" + NIST_HASH), framework="NIST CSF",
        edition="2.0 / OSCAL " + catalog["metadata"]["version"], title=catalog["metadata"]["title"],
        source=NIST_SOURCE, rights=NIST_RIGHTS, content_hash=NIST_HASH), controls


def available(db):
    # Never borrow activation from a later schema on the search path.
    return bool(db.scalar(text("""
      WITH scope AS (SELECT format('%I.', current_schema()) AS prefix)
      SELECT to_regclass(prefix||'control_catalogs') IS NOT NULL
       AND to_regclass(prefix||'catalog_controls') IS NOT NULL
       AND to_regclass(prefix||'finding_control_rules') IS NOT NULL
       AND to_regclass(prefix||'finding_control_decisions') IS NOT NULL
       AND to_regclass(prefix||'finding_control_targets') IS NOT NULL
       AND to_regprocedure(prefix||'am_control_catalog_guard_v1()') IS NOT NULL
       AND to_regprocedure(prefix||'am_control_decision_complete_v1()') IS NOT NULL
       AND EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='am_control_decision_complete'
         AND tgrelid=to_regclass(prefix||'finding_control_decisions')
         AND tgfoid=to_regprocedure(prefix||'am_control_decision_complete_v1()')
         AND tgenabled IN ('O','A') AND tgdeferrable AND tginitdeferred)
       AND (SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal
         AND tgname='am_control_catalog_guard' AND tgenabled IN ('O','A')
         AND tgfoid=to_regprocedure(prefix||'am_control_catalog_guard_v1()')
         AND tgrelid IN (to_regclass(prefix||'control_catalogs'),to_regclass(prefix||'catalog_controls'),
           to_regclass(prefix||'finding_control_rules'),to_regclass(prefix||'finding_control_decisions'),
           to_regclass(prefix||'finding_control_targets')))=5
      FROM scope
    """)))


def require_available(db):
    if not available(db):
        raise HTTPException(409, "Control mappings require coordinated database activation")


def catalog_data(row):
    return {key: getattr(row, key) for key in ("id", "framework", "edition", "title", "source", "rights", "content_hash", "installed_at")}


def catalogs(db):
    if not available(db):
        return dict(available=False, items=[])
    return dict(available=True, items=[catalog_data(r) for r in db.scalars(select(ControlCatalog).order_by(ControlCatalog.installed_at.desc(), ControlCatalog.id))])


def catalog_controls(db, catalog_id):
    require_available(db)
    row = db.get(ControlCatalog, catalog_id)
    if row is None:
        raise HTTPException(404, "Catalog release not found")
    return dict(catalog=catalog_data(row), controls=[dict(control_id=r.control_id, reference=r.reference, title=r.title, description=r.description)
        for r in db.scalars(select(CatalogControl).where(CatalogControl.catalog_id == catalog_id).order_by(CatalogControl.reference))])


def install_baseline(db, actor_id):
    try:
        # Revalidate after waiting; a revoked platform role cannot install.
        db.execute(text("SELECT pg_advisory_xact_lock(33015, 1)"))
        actor = db.scalar(select(User).where(User.id == actor_id).with_for_update(read=True, nowait=True).execution_options(populate_existing=True))
        if actor is None or not actor.is_active or not actor.is_sysadmin:
            raise HTTPException(403, "Platform administrator access changed")
        require_available(db)
        release, controls = baseline()
        existing = db.get(ControlCatalog, release["id"])
        if existing is not None:
            actual = catalog_controls(db, existing.id)
            if any(getattr(existing, k) != v for k, v in release.items()) or sorted(actual["controls"], key=lambda c: c["reference"]) != sorted(controls, key=lambda c: c["reference"]):
                raise HTTPException(409, "Installed catalog differs from its verified release; review required")
            db.rollback()
            return actual
        row = ControlCatalog(**release, installed_by=actor_id, installed_by_label=actor.name or actor.email)
        db.add(row)
        db.flush()
        db.add_all(CatalogControl(catalog_id=row.id, **c) for c in controls)
        record_event(db, "control_catalog_installed", org_id=None, actor=actor, item=row.title,
            details={"catalog_id": str(row.id), "source": row.source, "content_hash": row.content_hash, "control_count": len(controls)})
        db.commit()
        return catalog_controls(db, row.id)
    except DBAPIError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) in ("55P03", "40001", "40P01"):
            raise HTTPException(409, "Catalog installation is busy; reload before retrying") from exc
        raise
    except BaseException:
        db.rollback()
        raise


def finding_key(db, org_id, finding_id, *, writing=False):
    row = db.execute(select(Finding.id, Finding.source, Finding.domain, Finding.category,
        Finding.archived_at, Finding.suppression_id, Finding.consolidation_alias_id)
        .where(Finding.org_id == org_id, Finding.id == finding_id)).one_or_none()
    if row is None:
        raise HTTPException(404, "Finding not found")
    if writing and (row.archived_at or row.suppression_id or row.consolidation_alias_id):
        raise HTTPException(409, "Use an active primary finding to review its category mapping")
    return row


def rule_query(org_id, key):
    return select(FindingControlRule).where(FindingControlRule.org_id == org_id,
        FindingControlRule.source == (key.source or ""), FindingControlRule.domain == key.domain,
        FindingControlRule.category == (key.category or "")).execution_options(populate_existing=True)


def decisions_data(db, rows):
    if not rows:
        return {}
    catalogs_by_id = {r.id: r for r in db.scalars(select(ControlCatalog).where(ControlCatalog.id.in_({r.catalog_id for r in rows})))}
    targets = {r.id: [] for r in rows}
    query = select(FindingControlTarget.decision_id, CatalogControl.control_id, CatalogControl.reference, CatalogControl.title, CatalogControl.description).join(CatalogControl,
        (FindingControlTarget.catalog_id == CatalogControl.catalog_id) & (FindingControlTarget.control_id == CatalogControl.control_id)).where(
        FindingControlTarget.decision_id.in_(targets)).order_by(CatalogControl.reference)
    for target in db.execute(query):
        targets[target.decision_id].append(dict(control_id=target.control_id, reference=target.reference, title=target.title, description=target.description))
    return {r.id: dict(id=r.id, version=r.version, state=r.state, proposal_version=r.proposal_version,
        catalog=catalog_data(catalogs_by_id[r.catalog_id]), controls=targets[r.id], rationale=r.rationale,
        actor_label=r.actor_label, created_at=r.created_at) for r in rows}


def decision_data(db, row):
    return decisions_data(db, [row])[row.id] if row is not None else None


def _rule_result(db, rule, result):
    if rule is None:
        return result
    latest = db.scalar(select(FindingControlDecision).where(FindingControlDecision.rule_id == rule.id, FindingControlDecision.version == rule.version))
    effective = db.scalar(select(FindingControlDecision).where(FindingControlDecision.rule_id == rule.id,
        FindingControlDecision.version == rule.effective_version, FindingControlDecision.state == "approved")) if rule.effective_version else None
    result.update(version=rule.version, rule_id=rule.id, status="mapped" if effective else "unmapped",
        effective=decision_data(db, effective), proposal=decision_data(db, latest) if latest and latest.state == "proposed" else None)
    return result



def load_rule(db, org_id, rule_id, *, lock=False):
    query = select(FindingControlRule).where(FindingControlRule.org_id == org_id, FindingControlRule.id == rule_id)
    if lock:
        query = query.with_for_update(nowait=True)
    rule = db.scalar(query.execution_options(populate_existing=True))
    if rule is None:
        raise HTTPException(404, "Mapping rule not found")
    return rule


def read(db, org_id, finding_id):
    key = finding_key(db, org_id, finding_id)
    result = dict(available=available(db), context_kind="finding", finding_id=key.id, source=key.source, domain=key.domain,
        category=key.category, archived=bool(key.archived_at), inactive=bool(key.archived_at or key.suppression_id or key.consolidation_alias_id),
        version=0, rule_id=None, status="unmapped", effective=None, proposal=None)
    if not result["available"]:
        return result
    return _rule_result(db, db.scalar(rule_query(org_id, key)), result)


def read_rule(db, org_id, rule_id):
    require_available(db)
    rule = load_rule(db, org_id, rule_id)
    result = dict(available=True, context_kind="rule", finding_id=None, source=rule.source, domain=rule.domain,
        category=rule.category, archived=False, inactive=False, version=0, rule_id=None, status="unmapped", effective=None, proposal=None)
    return _rule_result(db, rule, result)


def read_many(db, org_id, findings):
    """Small page-only summaries; capture immutable decision versions once.

    Mapping review changes no list predicates or sort keys, so exact-count and
    seek caches stay valid. Each fresh page gets a fresh bounded summary.
    """
    ready = available(db)
    result = {f.id: ControlMappingSummary(available=ready) for f in findings}
    if not ready or not findings:
        return result

    def key(f):
        domain = f.domain.value if hasattr(f.domain, "value") else f.domain
        return f.source or "", domain, f.category or ""

    keys = {key(f) for f in findings}
    rules = db.execute(select(FindingControlRule.id, FindingControlRule.source, FindingControlRule.domain,
        FindingControlRule.category, FindingControlRule.version, FindingControlRule.effective_version).where(
        FindingControlRule.org_id == org_id, tuple_(FindingControlRule.source, FindingControlRule.domain, FindingControlRule.category).in_(keys))).all()
    versions = {(r.id, v) for r in rules for v in (r.version, r.effective_version) if v is not None}
    decisions = {(d.rule_id, d.version): d for d in db.execute(select(FindingControlDecision.rule_id,
        FindingControlDecision.version, FindingControlDecision.state, FindingControlDecision.catalog_id).where(
        FindingControlDecision.org_id == org_id, tuple_(FindingControlDecision.rule_id, FindingControlDecision.version).in_(versions)))} if versions else {}
    by_key = {(r.source, r.domain, r.category): r for r in rules}
    for finding in findings:
        rule = by_key.get(key(finding))
        if rule is None:
            continue
        latest = decisions.get((rule.id, rule.version))
        effective = decisions.get((rule.id, rule.effective_version))
        mapped = effective is not None and effective.state == "approved"
        result[finding.id] = ControlMappingSummary(status="mapped" if mapped else "unmapped",
            proposal_pending=bool(latest and latest.state == "proposed"), version=rule.version,
            catalog_id=effective.catalog_id if mapped else None)
    return result


def change(db, org_id, finding_id, actor_id, payload, action, *, rule_id=None):
    try:
        roles = (UserRole.admin, UserRole.auditor) if action == "propose" else (UserRole.admin,)
        member = authorize_org_write(db, org_id, actor_id, roles)
        require_available(db)
        if rule_id is not None:
            rule = load_rule(db, org_id, rule_id, lock=True)
            key = rule
            def normalized(value):
                domain = value.domain.value if hasattr(value.domain, "value") else value.domain
                return value.source or "", domain, value.category or ""
            if normalized(payload) != normalized(rule):
                raise HTTPException(409, "Review the exact retained category rule before changing it")
        else:
            key = finding_key(db, org_id, finding_id, writing=True)
            if (payload.source, payload.domain, payload.category) != (key.source, key.domain, key.category):
                raise HTTPException(409, "Finding source/category changed; reload before review")
            rule = db.scalar(rule_query(org_id, payload).with_for_update(nowait=True).execution_options(populate_existing=True))
        def read_result():
            return read_rule(db, org_id, rule_id) if rule_id is not None else read(db, org_id, finding_id)
        version = rule.version if rule else 0
        if payload.expected_version != version:
            raise HTTPException(409, "Control mapping changed; reload before retrying")
        latest = db.scalar(select(FindingControlDecision).where(FindingControlDecision.rule_id == rule.id, FindingControlDecision.version == version)) if rule else None
        targets = []
        if action == "propose":
            catalog_id = payload.catalog_id
            targets = sorted(payload.control_ids)
            if db.get(ControlCatalog, catalog_id) is None or db.scalar(select(func.count()).select_from(CatalogControl).where(CatalogControl.catalog_id == catalog_id, CatalogControl.control_id.in_(targets))) != len(targets):
                raise HTTPException(422, "Choose controls from one installed catalog release")
            previous = sorted(db.scalars(select(FindingControlTarget.control_id).where(FindingControlTarget.decision_id == latest.id)).all()) if latest else []
            if latest and latest.state == "proposed" and latest.catalog_id == catalog_id and previous == targets and latest.rationale == payload.rationale:
                result = read_result()
                db.rollback()
                return result
            state, proposal_version = "proposed", None
        elif action == "approve":
            if latest is None or latest.state != "proposed" or payload.proposal_version != latest.version:
                raise HTTPException(409, "The exact current proposal must be reviewed before approval")
            catalog_id = latest.catalog_id
            targets = list(db.scalars(select(FindingControlTarget.control_id).where(FindingControlTarget.decision_id == latest.id)))
            if not targets:
                raise HTTPException(409, "Proposal has no retained control targets")
            state, proposal_version = "approved", latest.version
        elif action == "withdraw":
            if rule is None or (rule.effective_version is None and latest.state == "withdrawn"):
                result = read_result()
                db.rollback()
                return result
            catalog_id = latest.catalog_id
            state, proposal_version = "withdrawn", None
        else:
            raise ValueError("Unsupported control review action")
        if rule is None:
            rule = FindingControlRule(org_id=org_id, source=payload.source or "", domain=payload.domain, category=payload.category or "", version=1)
            db.add(rule)
            db.flush()
        decision = FindingControlDecision(org_id=org_id, rule_id=rule.id, version=version + 1, state=state,
            catalog_id=catalog_id, proposal_version=proposal_version, rationale=payload.rationale,
            actor_id=actor_id, actor_label=member.user.name or member.user.email)
        db.add(decision)
        db.flush()
        db.add_all(FindingControlTarget(decision_id=decision.id, catalog_id=catalog_id, control_id=c) for c in targets)
        rule.version = decision.version
        if state == "approved":
            rule.effective_version = decision.version
        elif state == "withdrawn":
            rule.effective_version = None
        record_event(db, "finding_control_mapping_changed", org_id=org_id, actor=member.user,
            item=key.category or "Uncategorised finding", details={"rule_id": str(rule.id), "version": decision.version,
                "state": state, "source": payload.source, "domain": payload.domain, "category": payload.category,
                "catalog_id": str(catalog_id), "control_ids": [str(c) for c in targets], "rationale": payload.rationale})
        db.commit()
        return read_result()
    except DBAPIError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) in ("55P03", "40001", "40P01"):
            raise HTTPException(409, "Control mapping review is busy; reload before retrying") from exc
        raise
    except BaseException:
        db.rollback()
        raise
