"""Reading the Leijonat results service.

One plain, honestly identified HTTP request per call. If the service answers
403 we stop and report it; we do not retry it or dress the request up as
something it is not.
"""
import json
import time
import urllib.error
import urllib.request

from . import config

BASE = "https://tulospalvelu.leijonat.fi"


class Blocked(Exception):
    """The service refused us (403). Not retryable."""


class FetchError(Exception):
    """Anything else that went wrong."""


def _get_json(url, timeout=30, attempts=2):
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": config.USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Blocked(
                    f"403 Forbidden from {url} — the service is refusing automated "
                    f"requests from here. Use the userscript route instead."
                ) from e
            last = e
            if e.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
        if attempt + 1 < attempts:
            time.sleep(3)
    raise FetchError(f"Could not fetch {url}: {last}")


def series_url(dog=""):
    return (
        f"{BASE}/helpers/getgames?dwl=0&season={config.SEASON}"
        f"&subSerieId={config.SUBSERIE_ID}&teamid=0&districtid=0&gamedays=0"
        f"&dog={dog}&levelid=-1"
    )


def game_url(gameid):
    return f"{BASE}/gamereport/getgamereportdata?gameid={gameid}&season={config.SEASON}"


def fetch_series(dog=""):
    """Raw series response for one date (empty dog = whatever the service defaults to)."""
    return _get_json(series_url(dog))


def fetch_game(gameid):
    return _get_json(game_url(gameid))


def iter_games(series_payload):
    """Flatten the level groups of a series response into individual games."""
    for level in series_payload or []:
        for game in level.get("Games", []) or []:
            yield game


def dates_in(series_payload):
    found = set()
    for level in series_payload or []:
        found.update(level.get("GameDates", []) or [])
    return found
