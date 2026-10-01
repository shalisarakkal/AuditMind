import pytest

from app.services.client_info import client_details, describe_browser

CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"


@pytest.mark.parametrize(
    "agent, expected",
    [
        (CHROME_WIN, "Chrome on Windows"),
        (CHROME_WIN + " Edg/140.0", "Edge on Windows"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15", "Safari on macOS"),
        ("Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0", "Firefox on Linux"),
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 CriOS/140.0 Mobile Safari/604.1", "Chrome on iOS"),
        ("Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36", "Chrome on Android"),
        ("python-httpx/0.28.1", "python-httpx/0.28.1"),
        (None, None),
    ],
)
def test_describe_browser(agent, expected):
    assert describe_browser(agent) == expected


def test_client_details_leaves_out_blanks():
    assert client_details("203.0.113.9", CHROME_WIN) == {"ip": "203.0.113.9", "browser": "Chrome on Windows"}
    assert client_details(None, None) == {}
