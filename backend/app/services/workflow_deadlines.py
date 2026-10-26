"""Inclusive local calendar dates with immutable UTC expiry boundaries."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEADLINE_TIMEZONE = "America/New_York"


def deadline_today(now: datetime | None = None, zone: str = DEADLINE_TIMEZONE):
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("An aware instant is required")
    return instant.astimezone(ZoneInfo(zone)).date()


def deadline_now():
    return datetime.now(timezone.utc)


def validate_deadline_zone(value: str):
    if not value or len(value) > 100:
        raise ValueError("Provide a valid IANA timezone")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Provide a valid IANA timezone") from exc
    return value


def deadline_expiry(day: date, zone: str):
    """First instant after the selected local day (exclusive end boundary)."""
    tz = ZoneInfo(validate_deadline_zone(zone))
    if day.year >= 9999:
        raise ValueError("Deadline year must be before 9999")
    noon = datetime.combine(day, time(12), tzinfo=tz)
    if noon.astimezone(timezone.utc).astimezone(tz).date() != day:
        raise ValueError("This calendar day does not exist in the selected timezone")
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
