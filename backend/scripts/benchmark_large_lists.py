"""Read-only timings against the explicitly isolated local demo schema."""
import inspect
import argparse
import json
import time
from pathlib import Path
import sys
import subprocess
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from fastapi.params import Param
from app.core.config import settings
from scripts.demo import demo_url
from app.api.paging import DateRange, PageParams
from app.api.routes.assets import list_assets, asset_facets
from app.api.routes.findings import list_findings, finding_facets
from app.models.organization import Organization


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=[], help="Only run these named cases")
    parser.add_argument("--baseline", action="store_true", help="Compare pre-increment 1b2286f routes on the same database")
    args = parser.parse_args()
    asset_list, asset_options = list_assets, asset_facets
    finding_list, finding_options = list_findings, finding_facets
    if args.baseline:
        modules = []
        for name in ("assets", "findings"):
            source = subprocess.check_output(["git", "show", f"1b2286f:backend/app/api/routes/{name}.py"], text=True)
            module = types.ModuleType(f"benchmark_baseline_{name}")
            sys.modules[module.__name__] = module
            exec(compile(source, f"1b2286f:{name}.py", "exec"), module.__dict__)
            modules.append(module)
        asset_list, asset_options = modules[0].list_assets, modules[0].asset_facets
        finding_list, finding_options = modules[1].list_findings, modules[1].finding_facets
    engine = create_engine(demo_url(settings.DATABASE_URL))
    results = []
    try:
        with Session(engine) as db:
            org = db.scalar(select(Organization.id).where(Organization.name == "SA01"))
        if org is None:
            raise SystemExit("SA01 local demo organization not found")
        tag = None
        if any(case.startswith("assets_tag") for case in args.case):
            with engine.connect() as c:
                c.execute(text("SET TRANSACTION READ ONLY"))
                c.execute(text("SET LOCAL statement_timeout = '45s'"))
                tag = c.scalar(text("""SELECT tag FROM assets CROSS JOIN LATERAL unnest(tags) AS tag
                    WHERE org_id=:org AND archived_at IS NULL AND char_length(tag)>=3
                    GROUP BY tag ORDER BY count(*) DESC, tag LIMIT 1"""), {"org": org})
        for label, function, overrides in (
            ("assets_facets", asset_options, {}),
            ("findings_facets", finding_options, {}),
            ("assets_no_match", asset_list, {"q": "no-such-host-93c7"}),
            ("findings_no_match", finding_list, {"q": "no-such-host-93c7"}),
            ("assets_hostname_filter", asset_list, {"hostname": "NET-499979"}),
            ("assets_hostname_search", asset_list, {"q": "NET-499"}),
            ("findings_text_filter", finding_list, {"finding": "Deprecated"}),
            ("findings_common_search", finding_list, {"q": "Deprecated"}),
            ("assets_tag_search", asset_list, {"q": tag or "no-such-tag-93c7"}),
            ("assets_tag_filter", asset_list, {"tags": tag or "no-such-tag-93c7"}),
            ("assets_type_label", asset_list, {"q": "Network device"}),
            ("assets_common_type", asset_list, {"q": "server"}),
            ("assets_short", asset_list, {"q": "a"}),
        ):
            if args.case and label not in args.case:
                continue
            with Session(engine) as db:
                db.execute(text("SET TRANSACTION READ ONLY"))
                db.execute(text("SET LOCAL statement_timeout = '45s'"))
                arguments = {name: param.default.default if isinstance(param.default, Param) else param.default
                             for name, param in inspect.signature(function).parameters.items()}
                arguments.update(org_id=org, db=db, _=None)
                if "page" in arguments:
                    arguments["page"] = PageParams(100, 0)
                if "dates" in arguments:
                    arguments["dates"] = DateRange(None, None)
                arguments.update(overrides)
                started = time.perf_counter()
                try:
                    response = function(**arguments)
                    result = {"case": label, "milliseconds": round((time.perf_counter() - started) * 1000, 2),
                              "total": getattr(response, "total", None)}
                except Exception as exc:
                    result = {"case": label, "milliseconds": round((time.perf_counter() - started) * 1000, 2),
                              "error_type": type(exc).__name__}
                results.append(result)
                print(json.dumps(result), flush=True)
                db.rollback()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
