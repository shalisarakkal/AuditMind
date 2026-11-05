from datetime import datetime
from zoneinfo import ZoneInfo

from app.models.finding import Finding
from app.models.enums import Severity
from app.db.list_sort import severity_rank
from app.services.list_pages import Term, prefix_relation, ranked_groups


def test_deadline_prefixes_compare_instants_during_repeated_local_hour():
    early = datetime(2026,11,1,1,30,tzinfo=ZoneInfo("America/New_York"),fold=0)
    late = early.replace(fold=1)
    terms = [Term(Finding.due_expires_at)]
    assert prefix_relation([early],[datetime.fromisoformat(early.isoformat())],terms) == 0
    assert prefix_relation([late],[datetime.fromisoformat(late.isoformat())],terms) == 0
    assert prefix_relation([early],[late],terms) == -1
    assert prefix_relation([late],[early],terms) == 1


def test_repeated_local_hours_remain_distinct_deadline_groups():
    early = datetime(2026,11,1,1,30,tzinfo=ZoneInfo("America/New_York"),fold=0)
    groups = ranked_groups([(early,Severity.high,1),(early.replace(fold=1),Severity.high,1)],
        Finding.due_expires_at,Finding.severity,severity_rank(Finding.severity),Severity)
    assert len(groups) == 2
    assert sum(count for _prefix,_predicate,count in groups) == 2
    assert groups[0][0][0] != groups[1][0][0]
