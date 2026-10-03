"""Reading and writing the state file that is committed back to the repo."""
import json
import os

from . import config

VERSION = 1


def empty():
    return {"version": VERSION, "bootstrapped": False, "games": {}}


def load(path=None):
    path = path or config.STATE_PATH
    if not os.path.exists(path):
        return empty()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("version", VERSION)
    data.setdefault("bootstrapped", False)
    data.setdefault("games", {})
    return data


def save(state, path=None):
    path = path or config.STATE_PATH
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def game_entry(state, gameid):
    return state["games"].setdefault(
        str(gameid),
        {
            "date": None,
            "time": None,
            "rink": None,
            "home": None,
            "away": None,
            "home_id": None,
            "away_id": None,
            "sent": {},
            "period": 0,
            "score": [0, 0],
            "events": {},
        },
    )
