# Weekend Wickets Cricket Stats

Scrapes CricHeroes scorecards and turns them into CSVs for reporting.

| Script | Purpose |
| --- | --- |
| `download_scorecard.py` | Drives Chrome to download scorecard PDFs into `Match Data/` |
| `parse_scorecards.py` | Parses those PDFs into the CSVs under `data/` |
| `summary.py` | Streamlit season dashboard built on those CSVs |
| `report.py` | Renders the dashboard as a shareable PDF |

## Setup

```powershell
pip install playwright pdfplumber streamlit pandas reportlab
```

## Step 1 — Download scorecards

```powershell
python download_scorecard.py --from 2026-01 --to 2026-09 --dry-run   # preview the list
python download_scorecard.py --from 2026-01 --to 2026-09             # download
```

The window is year + month, inclusive. Defaults live at the top of the script
(`TEAM_NAME`, `START_YEAR/START_MONTH`, `END_YEAR/END_MONTH`), so as the season
goes on you can just bump `--to`.

Chrome is launched with remote debugging against a dedicated profile in
`.chrome-profile` — Chrome 136+ refuses remote debugging on your default profile.
The first run prompts you to log in to CricHeroes; the profile persists, so that's
a one-off.

Failed matches are retried (`--retries`, default 3) and then retried once more in
a second pass before being listed as failures.

## Step 2 — Parse into CSVs

```powershell
python parse_scorecards.py "Match Data\Scorecard_27306026.pdf" --print  # preview
python parse_scorecards.py "Match Data\Scorecard_27306026.pdf"          # one match
python parse_scorecards.py --all                                        # all matches
```

Only Weekend Wickets rows are written. Re-parsing a match replaces its existing
rows, so re-runs never duplicate.

## Step 3 — Season summary

```powershell
streamlit run summary.py
```

Sidebar filters: season, months, opposition, venue, result, and whether we batted
first or second. The "min innings" slider controls the qualification threshold for
rate-based boards (strike rate, average, economy) so one-innings flukes don't top
them.

Sections:

- **Headline** — played, won, lost, win %.
- **Season records** — biggest win by runs and by wickets, highest and lowest
  total, best defended score (the *lowest* total successfully defended batting
  first) and biggest chase (the highest target successfully run down).
- **Batting** — top 3 for runs, fours, sixes, strike rate, average.
- **Bowling** — top 3 for wickets, economy, strike rate (balls per wicket),
  average (runs per wicket).
- **Fielding** — top 3 by total dismissals (catches + stumpings + run outs +
  assists).
- **Partnerships** — highest individual stands, most partnership runs by player,
  and the most productive pairs.
- **Results** — the full match list.

Batting average uses dismissals, not innings, so not-outs are excluded from the
denominator. Every section also has an expander with the full underlying table.

### Sharing a PDF

Use **Download PDF report** in the sidebar (or the button at the bottom of the
page). The PDF is a landscape A4 report containing the headline numbers, season
records, every leaderboard and the full results table.

It always reflects the filters currently applied, so you can export, say, just the
Super Kings Trophy matches by filtering on opposition or month first.

## Column logic

### `matches.csv`
`match_id` comes from the PDF filename. `result` is `Won`/`Lost` derived from the
PDF's result line, and `Win loss Margin` is the text after "won by" (e.g.
`6 wickets`). `captain` is the Weekend Wickets captain from the Match Officials
table. `batted_first` plus the `our_*` / `opp_*` score columns drive the chase and
defence records on the summary page.

### `batting.csv`
Straight from our innings table. `Dismissal Type` is normalised from the Status
column into `Caught`, `Bowled`, `Stumped`, `LBW`, `Run Out`, `Caught & Bowled`,
`Not Out`, `Retired`.

### `bowling.csv`
Our bowlers, taken from the bowling table inside the **opposition's** innings.

### `fielding.csv`
Derived from how opposition batsmen were dismissed:

| Status in PDF | Credit |
| --- | --- |
| `c Fielder b Bowler` | catch to Fielder |
| `c&b Bowler` | catch to Bowler |
| `st Keeper b Bowler` | stumping to Keeper |
| `run out Fielder` | **run out** (direct hit) |
| `run out A / B` | **assisted run out** to both A and B |

### `partnerships.csv`
The PDF has no partnership table, so these are derived from Fall of Wickets.

- `Partnership` = score at this wicket minus score at the previous wicket, so it
  **includes extras**.
- `Balls` = balls bowled between the two falls, from the over stamps
  (`1.2 ov` → 8 balls). Also includes wides/no-balls, so it won't always equal the
  two batsmen's combined balls faced.
- `Unbeaten` = `Yes` only for the final stand when fewer than 10 wickets fell.
- Batsmen at the crease are tracked through the batting order, replacing whoever
  the Fall of Wickets entry names.

## MVP points

Based on CricHeroes' published **MVP 1.0** formula:
<https://blog.cricheroes.com/most-valuable-player-mvp-by-cricheroes/>

The base unit is **10 runs = 1 point**. There are no milestone bonuses (25/50/100),
duck penalties, dot-ball points, captain bonuses or win bonuses — those don't exist
in the CricHeroes system.

All the tables below are constants at the top of `parse_scorecards.py`.

### Batting MVP

```
base      = runs / 10
bonus%    = 8% (<=20 ov), 6% (<=35), 4% (<=50), 2% (beyond)
SR bonus  = (player SR / team SR) x bonus% x base     [only if player SR >= team SR]
MVP       = base + SR bonus
```

Team SR is the whole innings' strike rate. Strike rates below par are no longer
penalised by CricHeroes — they simply earn no bonus.

*Example:* 61 off 37 (SR 164.86) in a team innings of 116 off 100 (SR 116.0)
→ base 6.1, bonus (164.86/116) x 0.08 x 6.1 = 0.69 → **6.79**

### Bowling MVP

A wicket's value depends on match length and on how high the batsman batted.

| Match length | Runs per wicket |
| --- | --- |
| <=7 ov | 12 |
| <=12 ov | 14 |
| <=16 ov | 16 |
| <=20 ov | 18 |
| <=26 ov | 20 |
| <=40 ov | 22 |
| <=50 ov | 25 |
| beyond | 27 |

| Batting position | Multiplier |
| --- | --- |
| 1–4 | 100% |
| 5–8 | 80% |
| 9–11 | 60% |

```
wicket    = runs-per-wicket x position multiplier / 10
haul      = +0.5 (3 wkts), +1.0 (5 wkts), +1.5 (10 wkts)
maidens   = 1 wicket's worth per 1 maiden (<=7 ov), 2 (<=26), 3 (<=50), 6 (beyond)
eco bonus = (team eco / player eco) x (team eco - player eco) x bonus%
            [only if the bowler beat the team economy]
MVP       = wickets + haul + maidens + eco bonus
```

So in a T20 an opener's wicket is worth 1.8 points and a number 9's is 1.08.

*Example:* 3 top-order wickets in a T20 = 5.4, +0.5 haul, +0.12 economy → **6.02**

### Fielding MVP

A share of the same wicket value the bowler earned:

| Action | Share |
| --- | --- |
| Catch | 20% |
| Stumping | 20% |
| Run out (direct hit) | 100% |
| Assisted run out | 50% each |

CricHeroes publish no figure for assisted run outs; the 50% split is our own
choice, set by `ASSIST_SHARE` in the script.

### Caveats

- CricHeroes state plainly that they keep tweaking these tables, so treat the MVP
  columns as close approximations rather than exact app values.
- **MVP 2.0** superseded this in September 2026, replacing the flat formula with a
  ball-by-ball Pressure Index and Impact Score. CricHeroes publish the inputs but
  **no coefficients**, so it cannot be reproduced. Recent matches in the app may
  therefore show different numbers to these columns.
