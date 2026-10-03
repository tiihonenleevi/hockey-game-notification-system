#!/usr/bin/env python3
"""KaPa-51 game notifier.

    python run.py poll     # during the day: today's games and their events
    python run.py scan     # once a day: new or moved games in the weeks ahead
    python run.py test     # one request, prints whether the service answers

Everything is configured through environment variables (see kapa51/config.py).
Set DRY_RUN=1 to print messages instead of posting them.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

from kapa51 import config, detect, discord, messages, state as state_mod, tulospalvelu


def _archive(name, payload):
    if not config.ARCHIVE_RAW:
        return
    today = dt.datetime.now(detect.TZ).strftime("%Y-%m-%d")
    folder = os.path.join(config.ARCHIVE_DIR, today)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def cmd_test(_args):
    today = dt.datetime.now(detect.TZ).strftime("%Y-%m-%d")
    url = tulospalvelu.series_url(today)
    print(f"GET {url}")
    print(f"User-Agent: {config.USER_AGENT}")
    try:
        payload = tulospalvelu.fetch_series(today)
    except tulospalvelu.Blocked as e:
        print(f"\nBLOCKED: {e}")
        return 2
    except tulospalvelu.FetchError as e:
        print(f"\nFAILED: {e}")
        return 1
    games = list(tulospalvelu.iter_games(payload))
    print(f"\nOK — {len(games)} game(s) in the series for {today}.")
    for g in games:
        print(f"  {g.get('GameID')} {g.get('HomeTeamAbbrv')} – {g.get('AwayTeamAbbrv')}"
              f" {g.get('HomeGoals')}–{g.get('AwayGoals')} (status {g.get('GameStatus')})")
    return 0


def _our_games_today(payload):
    return [g for g in tulospalvelu.iter_games(payload) if detect.involves_team(g)]


def cmd_poll(args):
    st = state_mod.load()
    bootstrapping = not st.get("bootstrapped") or args.bootstrap
    if bootstrapping:
        st["bootstrapped"] = False
        print("Bootstrap run: recording current state, sending nothing.")

    now = dt.datetime.now(detect.TZ)
    today = now.strftime("%Y-%m-%d")
    notifications = []

    payload = tulospalvelu.fetch_series(today)
    _archive(f"series-{today}", payload)
    todays = _our_games_today(payload)
    notifications += detect.schedule_changes(st, todays, now=now)

    for game in todays:
        gid = str(game.get("GameID"))
        entry = st["games"].get(gid, {})
        if entry.get("sent", {}).get("final"):
            continue
        start = detect.start_datetime(game.get("GameDateDB"), game.get("GameTime"))
        if start and now < start - dt.timedelta(minutes=15) and game.get("GameStatus", 0) == 0:
            continue  # not close enough to puck drop to be worth a request
        report = tulospalvelu.fetch_game(gid)
        _archive(f"game-{gid}-{now.strftime('%H%M')}", report)
        notifications += detect.game_changes(st, report)
        time.sleep(1)

    return _finish(st, notifications, bootstrapping)


def cmd_scan(args):
    st = state_mod.load()
    bootstrapping = not st.get("bootstrapped") or args.bootstrap
    if bootstrapping:
        st["bootstrapped"] = False
        print("Bootstrap run: recording current state, sending nothing.")

    now = dt.datetime.now(detect.TZ)
    collected = []
    for offset in range(config.SCHEDULE_DAYS + 1):
        day = (now + dt.timedelta(days=offset)).strftime("%Y-%m-%d")
        payload = tulospalvelu.fetch_series(day)
        games = [g for g in tulospalvelu.iter_games(payload) if detect.involves_team(g)]
        if games:
            _archive(f"series-{day}", payload)
            collected += games
        time.sleep(config.SCAN_DELAY_SECONDS)

    print(f"Scanned {config.SCHEDULE_DAYS + 1} days, found {len(collected)} of our games.")
    notifications = detect.schedule_changes(st, collected, now=now)
    return _finish(st, notifications, bootstrapping)


def _finish(st, notifications, bootstrapping):
    if bootstrapping:
        st["bootstrapped"] = True
        state_mod.save(st)
        print(f"State seeded with {len(st['games'])} game(s).")
        return 0

    rendered = [messages.render(n) for n in notifications]
    for text in rendered:
        print("---")
        print(text)
    if rendered:
        discord.send_all(rendered)
    else:
        print("Nothing new.")
    state_mod.save(st)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["poll", "scan", "test"])
    parser.add_argument("--bootstrap", action="store_true",
                        help="record current state without sending anything")
    args = parser.parse_args(argv)

    try:
        return {"poll": cmd_poll, "scan": cmd_scan, "test": cmd_test}[args.command](args)
    except tulospalvelu.Blocked as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 2
    except tulospalvelu.FetchError as e:
        print(f"FETCH FAILED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
