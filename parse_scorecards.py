"""Parse CricHeroes scorecard PDFs into the CSVs under data/.

Only Weekend Wickets rows are emitted: our batting, our bowling, our fielding,
our partnerships, plus one summary row per match.

    python parse_scorecards.py "Match Data/Scorecard_27306026.pdf"   # single match
    python parse_scorecards.py --all                                 # every PDF
    python parse_scorecards.py --all --print                         # show, don't write

Re-parsing a match replaces its existing rows, so re-runs are safe.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber

TEAM_NAME = "WEEKEND WICKETS"
ROOT = Path(__file__).parent
PDF_DIR = ROOT / "Match Data"
DATA_DIR = ROOT / "data"

HEADERS = {
    "matches.csv": [
        "match_id", "date", "opposition", "venue", "result", "captain", "Win loss Margin",
        "batted_first", "our_runs", "our_wickets", "our_overs",
        "opp_runs", "opp_wickets", "opp_overs", "match_overs",
    ],
    "batting.csv": ["match_id", "player", "runs", "balls", "fours", "sixes", "SR", "Dismissal Type", "MVP"],
    "bowling.csv": ["match_id", "player", "overs", "maidens", "runs", "wickets", "0s", "4s", "6s", "Wd", "Nb", "Eco", "MVP"],
    "fielding.csv": ["match_id", "player", "catches", "run_outs", "assisted run_outs", "stumpings", "MVP"],
    "partnerships.csv": ["match_id", "wicket#", "player1_name", "player2_name", "Partnership", "Balls", "Unbeaten"],
}

# --- CricHeroes MVP 1.0, per https://blog.cricheroes.com/most-valuable-player-mvp-by-cricheroes/
# Base unit is 10 runs = 1 point. CricHeroes warn they keep tweaking the tables, so
# treat these as close approximations of the app's numbers rather than exact matches.
RUNS_PER_POINT = 10
# Runs a wicket is worth, by match length in overs.
WICKET_BASE_RUNS = [(7, 12), (12, 14), (16, 16), (20, 18), (26, 20), (40, 22), (50, 25), (99, 27)]
# Strike-rate bonus weighting, by match length in overs.
SR_BONUS_PCT = [(20, 0.08), (35, 0.06), (50, 0.04), (99, 0.02)]
# How many maidens are worth one wicket, by match length in overs.
MAIDENS_PER_WICKET = [(7, 1), (26, 2), (50, 3), (99, 6)]
# Top-order wickets are worth more than tail wickets.
POSITION_MULTIPLIER = [(4, 1.0), (8, 0.8), (11, 0.6)]
CATCH_SHARE = 0.20      # catcher/stumper takes 20% of the wicket's value
RUN_OUT_SHARE = 1.00    # direct hit earns the full wicket value
ASSIST_SHARE = 0.50     # no official figure published; split evenly

# Trailing stats on a batting row: R B M 4s 6s SR
BAT_TAIL = re.compile(r"\s(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+\.\d+)$")
# Trailing stats on a bowling row: O M R W 0s 4s 6s WD NB Eco
BOWL_TAIL = re.compile(
    r"\s(\d+(?:\.\d)?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+\.\d+)$"
)
INNINGS_HEAD = re.compile(r"^(.+?)\s+(\d+)/(\d+)\s+\((\d+(?:\.\d)?)\s*Ov\)\s+\((\d+)(?:st|nd|rd|th)\s+Innings\)")
FOW_ITEM = re.compile(r"(\d+)-(\d+)\s*\(([^,]+),\s*([\d.]+)\s*ov\)")
HAND = re.compile(r"\((?:RHB|LHB)\)")


def clean(text: str) -> str:
    """Drop the stray glyphs CricHeroes injects (e.g. 'st åVancheeswaran')."""
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^\x00-\x7f]", "", text).strip()


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", clean(name).lower())


# ------------------------------------------------------------------ extraction


def split_name_status(body: str) -> tuple[str, str]:
    """'2 Siddarth (RHB) st Vancheeswaran b Shankar' -> ('Siddarth', 'st Vancheeswaran b Shankar')."""
    body = re.sub(r"^\d+\s+", "", clean(body))
    parts = HAND.split(body, maxsplit=1)
    if len(parts) == 2:
        name, status = parts
    else:
        match = re.search(r"\b(c&b|c |st |b |lbw|run out|not out|retired)", body)
        if match:
            name, status = body[: match.start()], body[match.start():]
        else:
            name, status = body, ""
    name = re.sub(r"\((?:c|wk|c\s*&\s*wk|c and wk)\)", "", name, flags=re.I)
    return name.strip(" ()"), status.strip()


def dismissal_type(status: str) -> str:
    s = clean(status).lower()
    if not s:
        return ""
    if s.startswith("not out"):
        return "Not Out"
    if s.startswith("c&b") or s.startswith("c & b"):
        return "Caught & Bowled"
    if s.startswith("run out"):
        return "Run Out"
    if s.startswith("st "):
        return "Stumped"
    if s.startswith("lbw"):
        return "LBW"
    if s.startswith("c "):
        return "Caught"
    if s.startswith("b "):
        return "Bowled"
    if s.startswith("retired"):
        return "Retired"
    return clean(status)


def parse_innings(lines: list[str], start: int) -> tuple[dict, int]:
    """Read one innings block beginning at the header on lines[start]."""
    head = INNINGS_HEAD.match(clean(lines[start]))
    innings = {
        "team": head.group(1).strip(),
        "total": int(head.group(2)),
        "wickets": int(head.group(3)),
        "overs": head.group(4),
        "batting": [],
        "bowling": [],
        "fow": [],
        "to_bat": [],
    }

    section = None
    i = start + 1
    while i < len(lines):
        line = clean(lines[i])
        i += 1
        if not line or "cricheroes.com" in line:
            continue
        if INNINGS_HEAD.match(line):
            i -= 1
            break
        if line.startswith("No Batsman"):
            section = "bat"
            continue
        if line.startswith("No Bowler"):
            section = "bowl"
            continue
        if line.startswith("Fall of Wickets"):
            section = "fow"
            continue
        if line.startswith("To Bat:"):
            innings["to_bat"] = [p.strip() for p in line[7:].split(",") if p.strip()]
            section = None
            continue
        if line.startswith(("Extras:", "Total:")):
            section = None
            continue

        if section == "bat":
            tail = BAT_TAIL.search(line)
            if tail:
                name, status = split_name_status(line[: tail.start()])
                innings["batting"].append(
                    {
                        "player": name,
                        "status": status,
                        "runs": tail.group(1),
                        "balls": tail.group(2),
                        "fours": tail.group(4),
                        "sixes": tail.group(5),
                        "SR": tail.group(6),
                    }
                )
        elif section == "bowl":
            tail = BOWL_TAIL.search(line)
            if tail:
                name = re.sub(r"^\d+\s+", "", line[: tail.start()])
                name = re.sub(r"\((?:c|wk)\)", "", name, flags=re.I).strip()
                innings["bowling"].append(
                    {
                        "player": name,
                        "overs": tail.group(1),
                        "maidens": tail.group(2),
                        "runs": tail.group(3),
                        "wickets": tail.group(4),
                        "0s": tail.group(5),
                        "4s": tail.group(6),
                        "6s": tail.group(7),
                        "Wd": tail.group(8),
                        "Nb": tail.group(9),
                        "Eco": tail.group(10),
                    }
                )
        elif section == "fow":
            for m in FOW_ITEM.finditer(line):
                innings["fow"].append(
                    {
                        "score": int(m.group(1)),
                        "wicket": int(m.group(2)),
                        "player": m.group(3).strip(),
                        "over": m.group(4),
                    }
                )

    return innings, i


def parse_pdf(path: Path) -> dict:
    with pdfplumber.open(path) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]

    lines = [ln for page in pages for ln in page.splitlines()]
    text = "\n".join(clean(ln) for ln in lines)

    match = {
        "match_id": re.sub(r"\D", "", path.stem),
        "date": "",
        "venue": "",
        "result": "",
        "captains": {},
        "innings": [],
    }

    date = re.search(r"^Date\s+(\d{4}-\d{2}-\d{2})", text, re.M)
    if date:
        match["date"] = date.group(1)

    result = re.search(r"^Result\s+(.+)$", text, re.M)
    if result:
        match["result"] = result.group(1).strip()

    # The ground name wraps across the interleaved two-column header.
    venue_parts = []
    for i, ln in enumerate(lines):
        if clean(ln).startswith("Ground "):
            venue_parts.append(clean(ln)[7:])
            for follow in lines[i + 1: i + 4]:
                follow = clean(follow)
                if not follow or re.match(r"^(Result|Date|Total|Best|Match)\b", follow):
                    break
                if re.search(r"\d+/\d+\s*\(", follow):
                    continue
                venue_parts.append(follow)
                break
            break
    match["venue"] = " ".join(venue_parts).strip().rstrip(",")

    for cap in re.finditer(r"^\d+\s+(.+?)\s+\((.+?)\)\s+Captain\s*$", text, re.M):
        match["captains"][cap.group(2).strip()] = cap.group(1).strip()

    i = 0
    while i < len(lines):
        if INNINGS_HEAD.match(clean(lines[i])):
            innings, i = parse_innings(lines, i)
            match["innings"].append(innings)
        else:
            i += 1

    return match


# -------------------------------------------------------------- mvp scoring


def lookup(table: list[tuple], overs: float):
    for limit, value in table:
        if overs <= limit:
            return value
    return table[-1][1]


def match_length(match: dict) -> float:
    return max((float(i["overs"]) for i in match["innings"]), default=20.0)


def wicket_value(overs: float, position: int) -> float:
    """MVP points a wicket is worth, scaled down for lower-order batsmen."""
    base = lookup(WICKET_BASE_RUNS, overs)
    multiplier = lookup(POSITION_MULTIPLIER, position)
    return base * multiplier / RUNS_PER_POINT


def wicket_credits(innings: dict, overs: float) -> list[dict]:
    """Who earned what from each dismissal in this innings."""
    credits = []
    for position, batsman in enumerate(innings["batting"], start=1):
        status = clean(batsman["status"])
        low = status.lower()
        if not status or low.startswith(("not out", "retired")):
            continue

        value = wicket_value(overs, position)
        entry = {"value": value, "bowler": "", "catcher": "", "stumper": "", "runout": [], "mode": ""}

        if low.startswith(("c&b", "c & b")):
            entry["bowler"] = re.sub(r"^c\s*&\s*b\s*", "", status, flags=re.I).strip()
            entry["catcher"] = entry["bowler"]
            entry["mode"] = "caught"
        elif low.startswith("c "):
            fielder, _, bowler = status[2:].partition(" b ")
            entry["catcher"], entry["bowler"], entry["mode"] = fielder.strip(), bowler.strip(), "caught"
        elif low.startswith("st "):
            fielder, _, bowler = status[3:].partition(" b ")
            entry["stumper"], entry["bowler"], entry["mode"] = fielder.strip(), bowler.strip(), "stumped"
        elif low.startswith("run out"):
            entry["runout"] = [f.strip() for f in status[7:].split("/") if f.strip()]
            entry["mode"] = "run out"
        elif low.startswith("lbw"):
            entry["bowler"] = re.sub(r"^lbw\s*b?\s*", "", status, flags=re.I).strip()
            entry["mode"] = "lbw"
        elif low.startswith("b "):
            entry["bowler"], entry["mode"] = status[2:].strip(), "bowled"

        credits.append(entry)
    return credits


def batting_mvp(batsman: dict, innings: dict, overs: float) -> float:
    runs, balls = int(batsman["runs"]), int(batsman["balls"])
    basic = runs / RUNS_PER_POINT
    team_balls = balls_from_overs(innings["overs"])
    if not balls or not team_balls:
        return round(basic, 2)

    player_sr = runs / balls * 100
    team_sr = innings["total"] / team_balls * 100
    # Penalties were removed, so a below-par strike rate simply earns no bonus.
    bonus = 0.0
    if team_sr and player_sr >= team_sr:
        bonus = (player_sr / team_sr) * lookup(SR_BONUS_PCT, overs) * basic
    return round(basic + bonus, 2)


def bowling_mvp(bowler: dict, innings: dict, credits: list[dict], overs: float) -> float:
    taken = [c for c in credits if norm(c["bowler"]) == norm(bowler["player"])]
    points = sum(c["value"] for c in taken)

    wickets = int(bowler["wickets"])
    if wickets >= 10:
        points += 1.5
    elif wickets >= 5:
        points += 1.0
    elif wickets >= 3:
        points += 0.5

    maidens = int(bowler["maidens"])
    if maidens:
        base = lookup(WICKET_BASE_RUNS, overs) / RUNS_PER_POINT
        points += maidens * base / lookup(MAIDENS_PER_WICKET, overs)

    team_balls = balls_from_overs(innings["overs"])
    player_balls = balls_from_overs(bowler["overs"])
    if team_balls and player_balls:
        team_eco = innings["total"] / (team_balls / 6)
        player_eco = int(bowler["runs"]) / (player_balls / 6)
        if player_eco and player_eco < team_eco:
            points += (team_eco / player_eco) * (team_eco - player_eco) * lookup(SR_BONUS_PCT, overs)

    return round(points, 2)


# --------------------------------------------------------------- row building


def is_us(team: str) -> bool:
    return norm(TEAM_NAME) in norm(team)


def balls_from_overs(overs: str) -> int:
    """'4.4' -> 28 balls."""
    whole, _, part = str(overs).partition(".")
    return int(whole or 0) * 6 + int(part or 0)


def build_partnerships(innings: dict, match_id: str) -> list[dict]:
    order = [b["player"] for b in innings["batting"]] + innings["to_bat"]
    if len(order) < 2:
        return []

    at_crease = [order[0], order[1]]
    next_in = 2
    previous = 0
    previous_balls = 0
    rows = []

    for fall in sorted(innings["fow"], key=lambda f: f["wicket"]):
        balls = balls_from_overs(fall["over"])
        rows.append(
            {
                "match_id": match_id,
                "wicket#": fall["wicket"],
                "player1_name": at_crease[0],
                "player2_name": at_crease[1],
                "Partnership": fall["score"] - previous,
                "Balls": balls - previous_balls,
                "Unbeaten": "No",
            }
        )
        previous = fall["score"]
        previous_balls = balls

        out = norm(fall["player"])
        slot = next((j for j, p in enumerate(at_crease) if norm(p) == out), 0)
        at_crease[slot] = order[next_in] if next_in < len(order) else ""
        next_in += 1

    if innings["wickets"] < 10:
        rows.append(
            {
                "match_id": match_id,
                "wicket#": len(innings["fow"]) + 1,
                "player1_name": at_crease[0],
                "player2_name": at_crease[1],
                "Partnership": innings["total"] - previous,
                "Balls": balls_from_overs(innings["overs"]) - previous_balls,
                "Unbeaten": "Yes",
            }
        )
    return rows


def build_fielding(credits: list[dict], match_id: str) -> list[dict]:
    """Credit catches/stumpings/run-outs from how the opposition batsmen fell."""
    tally: dict[str, dict] = {}

    def bump(player: str, key: str, points: float) -> None:
        player = clean(player).strip()
        if not player:
            return
        tally.setdefault(
            player,
            {"catches": 0, "run_outs": 0, "assisted run_outs": 0, "stumpings": 0, "MVP": 0.0},
        )
        tally[player][key] += 1
        tally[player]["MVP"] += points

    for credit in credits:
        value = credit["value"]
        if credit["catcher"]:
            bump(credit["catcher"], "catches", value * CATCH_SHARE)
        if credit["stumper"]:
            bump(credit["stumper"], "stumpings", value * CATCH_SHARE)
        if credit["runout"]:
            # A lone name is a direct hit; a slash means it took two, so both assist.
            direct = len(credit["runout"]) == 1
            key = "run_outs" if direct else "assisted run_outs"
            share = RUN_OUT_SHARE if direct else ASSIST_SHARE
            for fielder in credit["runout"]:
                bump(fielder, key, value * share)

    return [
        {"match_id": match_id, "player": p, **c, "MVP": round(c["MVP"], 2)}
        for p, c in tally.items()
    ]


def build_rows(match: dict) -> dict[str, list[dict]]:
    mid = match["match_id"]
    ours = next((i for i in match["innings"] if is_us(i["team"])), None)
    theirs = next((i for i in match["innings"] if not is_us(i["team"])), None)
    if ours is None or theirs is None:
        raise ValueError(f"match {mid}: could not identify both innings")

    result = match["result"]
    won = is_us(result.split(" won ")[0]) if " won " in result else False
    margin = result.split(" won by ", 1)[1].strip() if " won by " in result else ""
    if not margin and result:
        margin = result

    captain = next((v for k, v in match["captains"].items() if is_us(k)), "")

    overs = match_length(match)
    credits = wicket_credits(theirs, overs)

    return {
        "matches.csv": [
            {
                "match_id": mid,
                "date": match["date"],
                "opposition": theirs["team"],
                "venue": match["venue"],
                "result": "Won" if won else ("Lost" if " won " in result else result),
                "captain": captain,
                "Win loss Margin": margin,
                "batted_first": "Yes" if is_us(match["innings"][0]["team"]) else "No",
                "our_runs": ours["total"],
                "our_wickets": ours["wickets"],
                "our_overs": ours["overs"],
                "opp_runs": theirs["total"],
                "opp_wickets": theirs["wickets"],
                "opp_overs": theirs["overs"],
                "match_overs": overs,
            }
        ],
        "batting.csv": [
            {
                "match_id": mid,
                "player": b["player"],
                "runs": b["runs"],
                "balls": b["balls"],
                "fours": b["fours"],
                "sixes": b["sixes"],
                "SR": b["SR"],
                "Dismissal Type": dismissal_type(b["status"]),
                "MVP": batting_mvp(b, ours, overs),
            }
            for b in ours["batting"]
        ],
        "bowling.csv": [
            {"match_id": mid, **b, "MVP": bowling_mvp(b, theirs, credits, overs)}
            for b in theirs["bowling"]
        ],
        "fielding.csv": build_fielding(credits, mid),
        "partnerships.csv": build_partnerships(ours, mid),
    }


# ----------------------------------------------------------------- csv output


def write_csv(filename: str, rows: list[dict], match_ids: set[str]) -> None:
    path = DATA_DIR / filename
    header = HEADERS[filename]
    existing = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as fh:
            existing = [r for r in csv.DictReader(fh) if r.get("match_id") not in match_ids]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerows(existing)
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="*", help="Scorecard PDFs to parse")
    parser.add_argument("--all", action="store_true", help="Parse every PDF in Match Data/")
    parser.add_argument("--print", dest="show", action="store_true", help="Print rows, write nothing")
    args = parser.parse_args()

    paths = [Path(p) for p in args.pdfs]
    if args.all:
        paths = sorted(PDF_DIR.glob("*.pdf"))
    if not paths:
        parser.error("give a PDF path or use --all")

    collected: dict[str, list[dict]] = {name: [] for name in HEADERS}
    match_ids: set[str] = set()

    for path in paths:
        try:
            rows = build_rows(parse_pdf(path))
        except Exception as exc:
            print(f"{path.name}: FAILED - {exc}", file=sys.stderr)
            continue
        match_ids.add(rows["matches.csv"][0]["match_id"])
        for name, items in rows.items():
            collected[name].extend(items)
        summary = rows["matches.csv"][0]
        print(
            f"{path.name}: {summary['date']} vs {summary['opposition']} "
            f"({summary['result']}) - "
            + ", ".join(f"{len(v)} {k.split('.')[0]}" for k, v in rows.items() if k != "matches.csv")
        )

    if args.show:
        for name, rows in collected.items():
            print(f"\n=== {name}")
            print(",".join(HEADERS[name]))
            for row in rows:
                print(",".join(str(row.get(c, "")) for c in HEADERS[name]))
        return 0

    for name, rows in collected.items():
        write_csv(name, rows, match_ids)
    print(f"\nWrote {len(match_ids)} match(es) into {DATA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
