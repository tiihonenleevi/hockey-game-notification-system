"""Finnish Discord messages for each kind of notification."""
import datetime as dt

from . import config

WEEKDAYS = ["ma", "ti", "ke", "to", "pe", "la", "su"]


def game_link(gid):
    return f"https://tulospalvelu.leijonat.fi/game?season={config.SEASON}&gameid={gid}&lang=fi"


def pretty_date(date_str, time_str):
    try:
        d = dt.date.fromisoformat(date_str)
        day = f"{WEEKDAYS[d.weekday()]} {d.day}.{d.month}."
    except (TypeError, ValueError):
        day = date_str or "?"
    clock = (time_str or "")[:5]
    return f"{day} klo {clock}" if clock else day


def matchup(n, bold_us=True):
    home, away = n.get("home") or "?", n.get("away") or "?"
    if bold_us:
        if n.get("home_id") == config.TEAM_ID:
            home = f"**{home}**"
        if n.get("away_id") == config.TEAM_ID:
            away = f"**{away}**"
    return f"{home} – {away}"


def clock(ev):
    """'2. erä 12:33' from the cumulative game clock."""
    period = ev.get("Period") or 1
    total = ev.get("GameTime") or 0
    within = total - (period - 1) * 1200
    if within < 0:
        within = total
    label = f"{period}. erä" if period <= 3 else "jatkoaika"
    return f"{label} {within // 60:02d}:{within % 60:02d}"


def _jersey_name(jersey, name):
    name = (name or "").strip()
    if not name or name == "null null":
        return None
    return f"#{jersey} {name}" if jersey else name


def _team_of(n, team_id):
    if team_id == n.get("home_id"):
        return n.get("home")
    if team_id == n.get("away_id"):
        return n.get("away")
    return "?"


GOAL_TYPES = {"YV": "ylivoima", "AV": "alivoima", "TM": "tyhjä maali", "VL": "voittolaukaus"}


def goal(n):
    ev = n["event"]
    ours = ev.get("TeamId") == config.TEAM_ID
    head = "🚨 **MAALI!**" if ours else "⚪ **Maali vastustajalle**"
    score = f"{n.get('home')} {ev.get('HomeTeamGoals')}–{ev.get('AwayTeamGoals')} {n.get('away')}"

    scorer = _jersey_name(ev.get("ScorerJersey"), ev.get("ScorerName")) or "?"
    assists = [
        _jersey_name(ev.get("FirstAssistJersey"), ev.get("FirstAssistName")),
        _jersey_name(ev.get("SecondAssistJersey"), ev.get("SecondAssistName")),
    ]
    assists = [a for a in assists if a]
    line = scorer + (f" ({', '.join(assists)})" if assists else "")

    extra = GOAL_TYPES.get(ev.get("GoalType") or "")
    tail = clock(ev) + (f" · {extra}" if extra else "")
    return f"{head} {score}\n{line}\n{tail}"


def penalty(n):
    ev = n["event"]
    team = _team_of(n, ev.get("TeamId"))
    who = _jersey_name(ev.get("Jersey"), ev.get("Name"))
    serving = _jersey_name(ev.get("SuffererJersey"), ev.get("SuffererNames"))
    if who is None:
        who = "joukkuerangaistus" + (f", kärsii {serving}" if serving else "")
    minutes = ev.get("PenaltyMinutesNumber") or "?"
    reason = ev.get("PenaltyReasonsFI") or ev.get("PenaltyReasonsEN") or ""
    return f"🟨 **Jäähy** – {team}: {who}, {minutes} min ({reason})\n{clock(ev)}"


def goalie(n):
    ev = n["event"]
    team = _team_of(n, ev.get("TeamId"))
    who = _jersey_name(ev.get("GoalkeeperJersey"), ev.get("GoalkeeperName")) or "?"
    return f"🥅 Maalivahti – {team}: {who}"


def other_event(n):
    ev = n["event"]
    return f"ℹ️ {ev.get('Type')} – {_team_of(n, ev.get('TeamId'))} · {clock(ev)}"


def period(n):
    score = n.get("score") or [0, 0]
    return (f"⏱️ **{n['period']}. erä alkoi** – "
            f"{n.get('home')} {score[0]}–{score[1]} {n.get('away')}")


def started(n):
    return f"🏒 **Ottelu alkoi** – {matchup(n)}\n{game_link(n['game'])}"


def _periods_without_total(rows):
    rows = [r for r in rows or [] if r]
    return rows[:-1] if len(rows) > 1 else rows


def final(n):
    home, away = n.get("home"), n.get("away")
    hg, ag = n.get("home_goals"), n.get("away_goals")
    ours_home = n.get("home_id") == config.TEAM_ID
    if hg is not None and ag is not None and ours_home is not None:
        our, their = (hg, ag) if ours_home else (ag, hg)
        verdict = "Voitto! 🎉" if our > their else ("Tappio." if our < their else "Tasapeli.")
    else:
        verdict = ""
    lines = [f"🏁 **Lopputulos: {home} {hg}–{ag} {away}**"]
    if verdict:
        lines.append(verdict)
    periods = _periods_without_total(n.get("periods"))
    if periods:
        lines.append("Erät: " + ", ".join(periods))
    saves = _periods_without_total(n.get("saves"))
    if saves:
        lines.append("Torjunnat: " + ", ".join(saves))
    pens = _periods_without_total(n.get("penalties"))
    if pens:
        lines.append("Jäähyminuutit: " + ", ".join(pens))
    lines.append(game_link(n["game"]))
    return "\n".join(lines)


def new_game(n):
    where = n.get("rink") or ""
    tail = f" · {where}" if where else ""
    return (f"📅 **Uusi ottelu kalenterissa**\n{matchup(n)}\n"
            f"{pretty_date(n.get('date'), n.get('time'))}{tail}")


FIELD_NAMES = {"date": "päivä", "time": "aika", "rink": "paikka"}


def schedule_change(n):
    bits = []
    for field, (old, new) in (n.get("changes") or {}).items():
        if field == "time":
            old, new = (old or "")[:5], (new or "")[:5]
        bits.append(f"{FIELD_NAMES.get(field, field)}: {old} → {new}")
    return f"🔁 **Otteluun muutos**\n{matchup(n)}\n" + "\n".join(bits)


def starting_soon(n):
    where = n.get("rink") or ""
    tail = f" · {where}" if where else ""
    return (f"⏰ **Ottelu alkaa pian** (n. {n.get('minutes')} min)\n{matchup(n)}\n"
            f"{pretty_date(n.get('date'), n.get('time'))}{tail}\n{game_link(n['game'])}")


def correction(n):
    ev = n["event"]
    kind = {"Goal": goal, "Penalty": penalty, "GK_start": goalie}.get(ev.get("Type"), other_event)
    return "✏️ **Korjattu kirjaus**\n" + kind(n)


def removed(n):
    return f"✏️ **Kirjaus poistettu** ({n.get('event_key')})\n{matchup(n)}"


RENDERERS = {
    "goal": goal,
    "penalty": penalty,
    "goalie": goalie,
    "other_event": other_event,
    "period": period,
    "started": started,
    "final": final,
    "new_game": new_game,
    "schedule_change": schedule_change,
    "starting_soon": starting_soon,
    "correction": correction,
    "removed": removed,
}


def render(n):
    renderer = RENDERERS.get(n.get("kind"))
    if renderer is None:
        return f"ℹ️ {n}"
    return renderer(n)
