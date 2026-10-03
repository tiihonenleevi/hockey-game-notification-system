#!/usr/bin/env python3
"""Replay the saved sample JSON through the detector, printing every message
that would have been posted. No network, no Discord.

    TEAM_ID=1368630031 python dryrun.py      # pretend Sepot is "our" team
"""
import copy
import datetime as dt
import json
import os

os.environ.setdefault("DRY_RUN", "1")

from kapa51 import config, detect, messages, state as state_mod  # noqa: E402

SAMPLES = os.path.join(os.path.dirname(__file__), "samples")


def load(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as f:
        return json.load(f)


def snapshot(report, n_events):
    """The same report as it would have looked n_events into the game."""
    snap = copy.deepcopy(report)
    logs = sorted(report["GameLogsUpdate"], key=lambda e: e.get("GameTime", 0))[:n_events]
    snap["GameLogsUpdate"] = logs
    header = snap["GamesUpdate"][0]
    if n_events == 0:
        header["GameStatus"], header["FinishedType"] = 0, 0
        snap["PeriodSummary"] = {"PlayedPeriods": 0}
    elif n_events < len(report["GameLogsUpdate"]):
        header["GameStatus"], header["FinishedType"] = 11, 0
        header["HomeTeam"] = dict(header["HomeTeam"])
        header["AwayTeam"] = dict(header["AwayTeam"])
        last_goal = [e for e in logs if e.get("Type") == "Goal"]
        header["HomeTeam"]["Goals"] = last_goal[-1]["HomeTeamGoals"] if last_goal else 0
        header["AwayTeam"]["Goals"] = last_goal[-1]["AwayTeamGoals"] if last_goal else 0
        snap["PeriodSummary"] = {"PlayedPeriods": max(e.get("Period", 1) for e in logs)}
    return snap


def show(step, notifications):
    print(f"\n=== {step} — {len(notifications)} message(s) ===")
    for n in notifications:
        print("·" * 50)
        print(messages.render(n))
    if not notifications:
        print("(nothing)")


def main():
    st = state_mod.empty()
    series = load("series_2026-09-11.json")
    upcoming = load("game_2707056_upcoming.json")
    finished = load("game_2707036_finished.json")
    all_messages = []

    def record(ns):
        all_messages.extend(messages.render(n) for n in ns)
        return ns

    # 1. First run ever: seed state silently.
    # Relabel the sample row to whichever team is configured, so the dry run
    # works when replaying a game KaPa-51 did not play in.
    template = copy.deepcopy(series[0]["Games"][0])
    template.update({"HomeTeam": config.TEAM_ID, "HomeTeamAbbrv": config.TEAM_NAME,
                     "AwayTeam": 1368626101, "AwayTeamAbbrv": "SaiPa Rähjät"})
    games = [template]
    show("Bootstrap run (should send nothing)",
         record(detect.schedule_changes(st, games, now=dt.datetime(2026, 9, 11, 9, 0, tzinfo=detect.TZ))))
    st["bootstrapped"] = True

    # 2. A game appears on the schedule, then the reminder before puck drop.
    newgame = copy.deepcopy(games[0])
    newgame.update({"GameID": 2707056, "GameDateDB": "2026-09-13", "GameTime": "12:00:00",
                    "AwayTeamAbbrv": "Sepot-vastustaja", "AwayTeam": 1368630032,
                    "RinkName": "Kangasniemen monitoimihalli"})
    show("New game added to the schedule",
         record(detect.schedule_changes(st, [newgame], now=dt.datetime(2026, 9, 12, 8, 0, tzinfo=detect.TZ))))

    moved = copy.deepcopy(newgame)
    moved["GameTime"] = "13:30:00"
    show("Game moved to a later time",
         record(detect.schedule_changes(st, [moved], now=dt.datetime(2026, 9, 12, 20, 0, tzinfo=detect.TZ))))

    show("45 minutes before puck drop",
         record(detect.schedule_changes(st, [moved], now=dt.datetime(2026, 9, 13, 12, 45, tzinfo=detect.TZ))))

    show("Report before the game starts (nothing yet)",
         record(detect.game_changes(st, snapshot(upcoming, 0))))

    # 3. Replay a real game in chunks, as polling would see it.
    total = len(finished["GameLogsUpdate"])
    for n in (2, 6, 11, 14, total):
        label = "Final whistle" if n == total else f"Poll with {n} events logged"
        show(label, record(detect.game_changes(st, snapshot(finished, n))))

    # 4. Polling again with no change must stay silent.
    show("Same data polled again (must be silent)",
         record(detect.game_changes(st, snapshot(finished, total))))

    # 5. A corrected scorer.
    corrected = copy.deepcopy(finished)
    for ev in corrected["GameLogsUpdate"]:
        if ev.get("Key") == "Goal_235":
            ev["ScorerName"], ev["ScorerJersey"] = "TIMONEN Aleksi", 34
    show("Scorer corrected afterwards", record(detect.game_changes(st, corrected)))

    print(f"\n{len(all_messages)} messages in total, "
          f"{len(st['games'])} games tracked, "
          f"{sum(len(g['events']) for g in st['games'].values())} events remembered.")


if __name__ == "__main__":
    main()
