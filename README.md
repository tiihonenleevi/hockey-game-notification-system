# KaPa-51 game notifier

Watches KaPa-51's games in U15 Valkoinen alkusarja, lohko 4 (season 2027) on
tulospalvelu.leijonat.fi and posts to Discord when something happens: a new game
on the schedule, a game moved, puck drop approaching, goals, penalties, period
changes and the final result. Messages are in Finnish.

Two ways to run it. **Start with A**; if the service refuses requests from
GitHub, fall back to **B**.

---

## A. GitHub Actions

### 1. Create the repo

Make a new GitHub repo and put these files in it. **Public is recommended** —
Actions minutes are free and unlimited for public repos, while a private repo
would burn through the monthly free allowance in a couple of weekends. Nothing
secret lives in the files; the webhook URL is stored as a secret, not committed.

### 2. Find out whether it's blocked

Actions tab → **Test access to tulospalvelu** → *Run workflow*. It makes one
request and prints the result.

- `OK — N game(s)…` → carry on with step 3.
- `BLOCKED: 403 …` → the service refuses GitHub's servers. Skip to part B.

### 3. Create the Discord webhook

In Discord: channel → Edit Channel → Integrations → Webhooks → New Webhook →
Copy Webhook URL.

### 4. Store it in the repo

Settings → Secrets and variables → Actions:

- **New repository secret**: name `DISCORD_WEBHOOK_URL`, value the webhook URL.
- Optionally **New variable**: name `CONTACT`, value your email. It goes in the
  request's User-Agent so the site's operators can see who is calling and reach
  you instead of just blocking you.

### 5. Seed the state (important)

Actions → **Scan schedule** → *Run workflow* → tick **bootstrap**.

This records every game currently on the schedule without sending anything.
Without it, the first real run would post the entire season's history at once.

### 6. Check it posts

Actions → **Poll games** → *Run workflow* (bootstrap **off**) on a day when a
game is on. Or temporarily reset: delete `state.json`, run **Poll games** with
bootstrap off right after a game, and it will post that game's events.

### 7. Leave the schedules on

`poll.yml` runs every 5 minutes during likely game hours (weekends 07–22
Helsinki, weekday evenings). `scan.yml` runs once a day and looks a month ahead.
Adjust the cron lines if your team's games fall outside those windows.

---

## B. Browser userscript

Use this if step 2 said BLOCKED. It runs in your own browser on a tulospalvelu
tab, reads the same data the page itself loads, and posts to Discord. A computer
with that tab open has to be on during games — an old laptop at home is enough.

1. Install Tampermonkey in your browser.
2. Create a new script and paste in `userscript/kapa51-notifier.user.js`.
3. Put your webhook URL in `CONFIG.WEBHOOK` at the top, and save.
4. Open <https://tulospalvelu.leijonat.fi/serie?season=2027&lid=94&did=9&ssid=3505&lang=fi>
   and leave the tab open. A small box in the bottom right shows each poll.
5. The first poll seeds state silently, same as the bootstrap run above. The
   Tampermonkey menu has a "reset state" command if you want to replay.

It polls once a minute and only fetches game reports when a game is close to
starting or under way.

---

## Trying it without any of that

```bash
python3 dryrun.py                               # replays samples/, prints messages
TEAM_ID=1368630031 TEAM_NAME=Sepot python3 dryrun.py   # replay the finished sample game
DRY_RUN=1 python3 run.py poll                   # real fetch, prints instead of posting
```

No dependencies — standard library only, Python 3.9+.

## What's where

| Path | |
|---|---|
| `run.py` | entry point: `poll`, `scan`, `test` |
| `kapa51/tulospalvelu.py` | the two HTTP calls |
| `kapa51/detect.py` | works out what's new; all pure functions |
| `kapa51/messages.py` | the Finnish message texts — edit these to taste |
| `kapa51/state.py` | `state.json` read/write |
| `kapa51/discord.py` | posting, with rate-limit handling |
| `dryrun.py` | replays `samples/` through the detector |
| `samples/` | real captured JSON, used by the dry run |
| `docs/data-format.md` | field-by-field notes on both endpoints |
| `archive/` | every raw response, kept for later analysis |

## Settings

All environment variables, all optional (see `kapa51/config.py`):
`TEAM_ID`, `TEAM_NAME`, `SEASON`, `SUBSERIE_ID`, `SCHEDULE_DAYS`,
`STARTING_SOON_MINUTES`, `CONTACT`, `DRY_RUN`, `ARCHIVE_RAW`.

## Things to know

- **Cron in Actions is approximate.** Runs can be delayed by several minutes
  when GitHub is busy, so a goal may arrive late. Nothing is lost, just slower.
- **Scheduled workflows stop after 60 days** of no repository activity. The
  bot's own commits don't always reset that timer, so push something
  occasionally, or re-enable the workflows when GitHub emails you.
- **Duplicates.** Every goal and penalty has a stable ID from the service, and
  the state file remembers which ones have been seen, so a repeated poll stays
  silent. Edited entries are re-posted once as "Korjattu kirjaus".
- **Period changes** are inferred from the period counter, because the data has
  no period-start event.
- **`archive/` grows** by a few hundred KB a season. It's there so a later stats
  feature has history to work with; set `ARCHIVE_RAW=0` to turn it off.
