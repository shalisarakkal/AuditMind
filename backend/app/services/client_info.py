"""Where a sign-in comes from, in a few words for Activity and the "Where
you're signed in" list: the address, and the browser and system its
user-agent names ("Chrome on Windows")."""

import re

# Checked in order: Edge and Opera also say "Chrome", Chrome also says "Safari".
_BROWSERS = (
    ("Edge", r"Edg(e|A|iOS)?/"),
    ("Opera", r"OPR/|Opera"),
    ("Firefox", r"Firefox/|FxiOS/"),
    ("Chrome", r"Chrome/|CriOS/"),
    ("Safari", r"Safari/"),
)
_SYSTEMS = (
    ("iOS", r"iPhone|iPad|iPod"),
    ("Android", r"Android"),
    ("Windows", r"Windows"),
    ("macOS", r"Mac OS X|Macintosh"),
    ("ChromeOS", r"CrOS"),
    ("Linux", r"Linux"),
)


def describe_browser(user_agent: str | None) -> str | None:
    """"Chrome on Windows"; the part it can't tell is left out; None for
    no user-agent (a script, say: "python-httpx/0.28" is kept as it is)."""
    if not user_agent:
        return None
    browser = next((name for name, pattern in _BROWSERS if re.search(pattern, user_agent)), None)
    system = next((name for name, pattern in _SYSTEMS if re.search(pattern, user_agent)), None)
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or user_agent[:60]


def client_details(ip: str | None, user_agent: str | None) -> dict:
    """For an event's details: {"ip": ..., "browser": ...}, without blanks."""
    return {key: value for key, value in (("ip", ip), ("browser", describe_browser(user_agent))) if value}
