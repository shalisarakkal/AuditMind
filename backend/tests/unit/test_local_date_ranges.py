from datetime import date, datetime
import pytest
from sqlalchemy import column
from app.api.paging import DateRange


@pytest.mark.parametrize("day,zone,start,end", [
    ("2026-10-25","Asia/Kolkata","2026-10-24T18:30:00+00:00","2026-10-25T18:30:00+00:00"),
    ("2026-03-08","America/New_York","2026-03-08T05:00:00+00:00","2026-03-09T04:00:00+00:00"),
    ("2026-11-01","America/New_York","2026-11-01T04:00:00+00:00","2026-11-02T05:00:00+00:00"),
])
def test_inclusive_browser_days(day, zone, start, end):
    conditions=DateRange(date.fromisoformat(day),date.fromisoformat(day),zone).conditions(column('created_at'))
    assert conditions[0].right.value==datetime.fromisoformat(start)
    assert conditions[1].right.value==datetime.fromisoformat(end)


def test_one_sided_and_empty_ranges():
    assert len(DateRange(date(2026,10,25),None,'UTC').conditions(column('created_at')))==1
    assert len(DateRange(None,date(2026,10,25),'UTC').conditions(column('created_at')))==1
    assert DateRange(None,None).conditions(column('created_at'))==[]


@pytest.mark.parametrize("start,end,zone", [
    (date(2026,10,26),date(2026,10,25),'UTC'),
    (None,None,'Bad/Timezone'),
    (None,date(9999,12,31),'UTC'),
    (date(2011,12,30),None,'Pacific/Apia'),
])
def test_invalid_ranges_fail_closed(start,end,zone):
    with pytest.raises((ValueError,OverflowError)):
        DateRange(start,end,zone)
