# tulospalvelu.leijonat.fi — data format reference

Based on real responses captured 2026-09-11 (see `samples/`).

## KaPa-51 identifiers

| What | Value |
|---|---|
| Team ID (U15 Valkoinen, this series) | `1368625759` |
| Association ID (Kangasniemen Palloilijat) | `10113275` |
| Series (`subSerieId`) | `3505` — "U15 Valkoinen alkusarja, lohko 4" |

Match on **team ID**, not on name — names differ between endpoints (`HomeTeamAbbrv` vs `HomeTeam.Name`).

---

## 1. Series endpoint — `helpers/getgames`

Top level is an **array of level groups**; games are nested in `[i].Games[]`.

| Field | Example | Meaning |
|---|---|---|
| `GameID` | `2707068` | Key for the game report endpoint |
| `GameDateDB` | `"2026-09-11"` | ISO date (also `GameDate` = `"11.09.2026"`) |
| `GameTime` | `"18:00:00"` | Local start time (**not** elapsed time here) |
| `TimeZone` | `"Europe/Helsinki"` | |
| `HomeTeam` / `AwayTeam` | `1368625759` | Team IDs (plain ints) |
| `HomeTeamAbbrv` / `AwayTeamAbbrv` | `"KaPa-51"`, `"SaiPa Rähjät"` | Display names |
| `HomeGoals` / `AwayGoals` | `2`, `0` | Current score |
| `GameStatus` | `11` | See status table below |
| `FinishedType` | `0` | 0 = not finished |
| `GameEffTime` | `967` | Elapsed game clock in seconds (16:07) |
| `RinkName` | `"Kangasniemi"` | |
| `PeriodSummary.PlayedPeriods` | `1` | **Current** period number (1 at 16:07) |
| `PeriodSummary.PeriodGoals` | `{"Home":[2],"Away":[0]}` | Goals per period |
| `DeniedResults` / `DeniedStats` | `0` | Presumably 1 if the series hides results |

**Open question:** with `dog=2026-09-11` the response only contained that date (`GameDates: ["2026-09-11"]`). We still need the parameters that return the **whole season's schedule** (try `dog=` empty, or `teamid=1368625759`).

---

## 2. Game report endpoint — `gamereport/getgamereportdata`

### `GamesUpdate[0]` — game header

| Field | Upcoming (2707056) | Finished (2707036) |
|---|---|---|
| `StartDate` / `StartTime` | `"13.09.2026"` / `"12:00:00"` | `"06.09.2026"` / `"12:00:00"` |
| `GameTime` | `0` | `3600` — elapsed seconds (differs from series `GameTime`!) |
| `Arena` | `"Kangasniemen monitoimihalli"` | `"Nurmeksen jäähalli Oy"` |
| `HomeTeam` / `AwayTeam` | `{Name, Goals, Id, AssId, Image}` | same |
| `GameStatus` | `0` | `2` |
| `FinishedType` | `0` | `1` |
| `Spectators` | `0` | `53` |

### `GameLogsUpdate[]` — the event stream

Every event has `Type`, `TeamId`, `Period`, and `GameTime` (**cumulative seconds from game start**, e.g. 2436 = 40:36 = 0:36 into period 3). Three types appeared in the finished game (22 events):

**`Goal`** (12) — has a stable unique `Key` (`"Goal_32"`)
- `ScorerName`, `ScorerJersey`
- `FirstAssistName/Jersey`, `SecondAssistName/Jersey` — empty assist = name `" "`, jersey `0`
- `HomeTeamGoals`, `AwayTeamGoals` — running score after this goal (verified consistent)
- `GoalType` — `""` = even strength, `"AV"` = shorthanded (confirmed against `PeriodSHGoals`). Expect `"YV"` (power play) and `"TM"` (empty net) too — unconfirmed.

**`Penalty`** (8) — has a unique `Key` (`"Penalty_8"`)
- `Name`, `Jersey` — penalised player; **team penalties show `"null null"` / `0`**
- `SuffererNames`, `SuffererJersey` — who serves it (use this for team penalties)
- `PenaltyMinutesNumber` (`2`), `PenaltyReasonsFI` (`"Kampitus"`), `PenaltyReasonsEN` (`"Tripping"`)

**`GK_start`** (2) — starting goalie per team, **no `Key`**
- `GoalkeeperName`, `GoalkeeperJersey`
- Needs a synthesized dedup key, e.g. `GK_start_<TeamId>_<PlayerLinkID>_<GameTime>`

Not seen yet (need a live/other game to confirm): goalie changes mid-game, timeouts, penalty shots, overtime/shootout events (`WinningShots[]`).

### `PeriodSummary` — per-period stats

Arrays of `"home-away"` strings, one per period **plus a final total entry**:
`PeriodGoals` `["5-2","0-0","3-2","8-4"]`, plus `PeriodSaves`, `PeriodPenMins`, `PeriodPPMins`, `PeriodPPGoals`, `PeriodSHGoals`. Good material for the final-result message.

### Other
- `Referees[]` — `{RefereeRole, RefereeName}`
- `GoalkeeperSummary[]` — saves per goalie per period (`Period: 0` = total)
- `GameRules` `"60;0;3;20;..."` — 60 min, 3 periods × 20 min

---

## GameStatus values observed

| Value | Where | State |
|---|---|---|
| `0` | report | Not started |
| `11` | series | Live — 1st period, 16:07 elapsed |
| `2` + `FinishedType 1` | report | Finished (regulation, presumably) |

Other codes (intermissions, later periods, OT, shootout) are unknown. The script should treat `GameStatus == 0` as "not started", `FinishedType != 0` as "finished", and anything else as "live" — and log unfamiliar codes rather than rely on them.

---

## How each notification maps to the data

| Notification | Detection |
|---|---|
| New game on schedule | `GameID` for KaPa-51 not in saved state |
| Schedule change | Saved date / time / rink differs from current |
| Game about to start | Now within N minutes of `GameDateDB` + `GameTime`, not yet notified |
| Game started | `GameStatus` leaves `0` (or first event appears) |
| Goal / penalty / goalie | Event `Key` not in saved state |
| Correction | Saved `Key` exists but content changed (scorer fixed), or disappeared (goal disallowed) |
| Period change | `PlayedPeriods` increases — **there is no explicit period event** |
| Final result | `FinishedType` becomes non-zero |
