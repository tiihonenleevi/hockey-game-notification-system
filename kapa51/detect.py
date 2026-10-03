"""Working out what is new since the last run.

Pure functions: they take the previous state plus freshly fetched data and
return (notifications, updated state). Nothing here touches the network, so
all of it can be replayed against the files in samples/.
"""
import datetime as dt
import hashlib
import json
from zoneinfo import ZoneInfo

from . import config

TZ = ZoneInfo(config.TIMEZONE)

# Fields that make an event "the same event" if they change -> a correction.
FINGERPRINT_FIELDS = (
    "Period", "GameTime", "TeamId",
    "ScorerName", "ScorerJersey", "FirstAssistName", "SecondAssistName",
    "GoalType", "HomeTeamGoals", "AwayTeamGoals",
    "Name", "Jersey", "SuffererNames", "SuffererJersey",
    "PenaltyMinutesNumber", "PenaltyReasonsFI",
    "GoalkeeperName", "GoalkeeperJersey",
)


def involves_team(game):
    return config.TEAM_ID in (game.get("HomeTeam"), game.get("AwayTeam"))


def start_datetime(date_str, time_str):
    """date_str 'YYYY-MM-DD', time_str 'HH:MM:SS' -> aware datetime."""
    if not date_str or not time_str:
        return None
    try:
        naive = dt.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return naive.replace(tzinfo=TZ)


def event_key(ev):
    """Stable identity for an event. Goals and penalties carry one already."""
    if ev.get("Key"):
        return ev["Key"]
    return "{}_{}_{}_{}".format(
        ev.get("Type"), ev.get("TeamId"), ev.get("GameTime"), ev.get("PlayerLinkID")
    )


def fingerprint(ev):
    payload = {k: ev.get(k) for k in FINGERPRINT_FIELDS if k in ev}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _game_facts(game):
    return {
        "date": game.get("GameDateDB"),
        "time": game.get("GameTime"),
        "rink": game.get("RinkName"),
        "home": game.get("HomeTeamAbbrv"),
        "away": game.get("AwayTeamAbbrv"),
        "home_id": game.get("HomeTeam"),
        "away_id": game.get("AwayTeam"),
    }


def schedule_changes(state, games, now=None):
    """New games, moved games and games about to start, from series data."""
    now = now or dt.datetime.now(TZ)
    out = []
    bootstrapping = not state.get("bootstrapped")

    for game in games:
        if not involves_team(game):
            continue
        gid = str(game.get("GameID"))
        facts = _game_facts(game)
        entry = state["games"].get(gid)

        if entry is None:
            entry = state["games"].setdefault(gid, {
                "sent": {}, "period": 0, "score": [0, 0], "events": {}
            })
            entry.update(facts)
            if not bootstrapping:
                out.append({"kind": "new_game", "game": gid, **facts})
            entry["sent"]["new_game"] = True
        else:
            moved = {
                k: (entry.get(k), facts[k])
                for k in ("date", "time", "rink")
                if entry.get(k) is not None and entry.get(k) != facts[k]
            }
            entry.update(facts)
            if moved and not bootstrapping:
                out.append({"kind": "schedule_change", "game": gid,
                            "changes": moved, **facts})
                # A moved game deserves a fresh reminder.
                entry["sent"].pop("starting_soon", None)

        start = start_datetime(facts["date"], facts["time"])
        if start and not entry["sent"].get("starting_soon"):
            minutes_away = (start - now).total_seconds() / 60
            if 0 <= minutes_away <= config.STARTING_SOON_MINUTES:
                if not bootstrapping:
                    out.append({"kind": "starting_soon", "game": gid,
                                "minutes": int(minutes_away), **facts})
                entry["sent"]["starting_soon"] = True
            elif minutes_away < 0:
                # Already started before we ever looked; don't announce it later.
                entry["sent"]["starting_soon"] = True

    return out


def game_changes(state, report):
    """Everything inside one game report: start, events, periods, final score."""
    out = []
    bootstrapping = not state.get("bootstrapped")

    header = (report.get("GamesUpdate") or [{}])[0]
    gid = str(header.get("Id"))
    if gid in (None, "None"):
        return out

    entry = state["games"].setdefault(gid, {
        "sent": {}, "period": 0, "score": [0, 0], "events": {}
    })
    home = (header.get("HomeTeam") or {})
    away = (header.get("AwayTeam") or {})
    entry.setdefault("home", home.get("Name"))
    entry.setdefault("away", away.get("Name"))
    entry["home_id"] = entry.get("home_id") or home.get("Id")
    entry["away_id"] = entry.get("away_id") or away.get("Id")

    context = {
        "game": gid,
        "home": entry.get("home") or home.get("Name"),
        "away": entry.get("away") or away.get("Name"),
        "home_id": home.get("Id"),
        "away_id": away.get("Id"),
    }

    status = header.get("GameStatus", 0)
    finished = bool(header.get("FinishedType", 0))

    if status != 0 and not entry["sent"].get("started"):
        if not bootstrapping and not finished:
            out.append({"kind": "started", **context})
        entry["sent"]["started"] = True

    # --- events -------------------------------------------------------
    logs = report.get("GameLogsUpdate") or []
    seen = {}
    for ev in logs:
        key = event_key(ev)
        seen[key] = fingerprint(ev)

    known = entry.get("events", {})
    new_events, corrections = [], []
    for ev in sorted(logs, key=lambda e: (e.get("GameTime", 0), event_key(e))):
        key = event_key(ev)
        if key not in known:
            new_events.append(ev)
        elif known[key] != seen[key]:
            corrections.append(ev)

    removed = [k for k in known if k not in seen]

    if not bootstrapping:
        for ev in new_events:
            kind = {"Goal": "goal", "Penalty": "penalty", "GK_start": "goalie"}.get(
                ev.get("Type"), "other_event"
            )
            out.append({"kind": kind, "event": ev, **context})
        for ev in corrections:
            out.append({"kind": "correction", "event": ev, **context})
        for key in removed:
            out.append({"kind": "removed", "event_key": key, **context})

    entry["events"] = seen

    # --- period changes ----------------------------------------------
    played = (report.get("PeriodSummary") or {}).get("PlayedPeriods", 0) or 0
    if played > entry.get("period", 0):
        if not bootstrapping and not finished and played > 1:
            before = [e for e in logs if (e.get("Period") or 1) < played]
            out.append({"kind": "period", "period": played,
                        "score": _score_from_logs(before, home.get("Id")), **context})
        entry["period"] = played

    # --- final ---------------------------------------------------------
    if finished and not entry["sent"].get("final"):
        if not bootstrapping:
            out.append({
                "kind": "final",
                "home_goals": home.get("Goals"),
                "away_goals": away.get("Goals"),
                "periods": _period_strings(report, "PeriodGoals", "Goals"),
                "saves": _period_strings(report, "PeriodSaves", "Saves"),
                "penalties": _period_strings(report, "PeriodPenMins", "PenMins"),
                "finished_type": header.get("FinishedType"),
                **context,
            })
        entry["sent"]["final"] = True

    entry["score"] = [home.get("Goals", 0), away.get("Goals", 0)]
    return sorted(out, key=_order)


def _order(n):
    """Chronological order, so '2. erä alkoi' lands before that period's goals."""
    kind = n.get("kind")
    if kind == "started":
        return (-1, 0)
    if kind == "final":
        return (99, 10 ** 9)
    if kind == "removed":
        return (98, 0)
    if kind == "period":
        return (n.get("period", 0), -1)
    ev = n.get("event") or {}
    return (ev.get("Period") or 0, ev.get("GameTime") or 0)


def _score_from_logs(logs, home_id):
    score = [0, 0]
    for ev in logs:
        if ev.get("Type") == "Goal":
            if ev.get("HomeTeamGoals") is not None:
                score = [ev["HomeTeamGoals"], ev["AwayTeamGoals"]]
            elif ev.get("TeamId") == home_id:
                score[0] += 1
            else:
                score[1] += 1
    return score


def _period_strings(report, field, inner):
    rows = (report.get("PeriodSummary") or {}).get(field) or []
    return [r.get(inner) for r in rows]
