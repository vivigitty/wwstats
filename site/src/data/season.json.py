"""Observable Framework data loader: emit every CSV as one typed JSON payload."""

import json
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[3] / "data"

NUMERIC = {
    "matches": ["our_runs", "our_wickets", "our_overs", "opp_runs", "opp_wickets", "opp_overs", "match_overs"],
    "batting": ["runs", "balls", "fours", "sixes", "SR", "MVP"],
    "bowling": ["overs", "maidens", "runs", "wickets", "0s", "4s", "6s", "Wd", "Nb", "Eco", "MVP"],
    "fielding": ["catches", "run_outs", "assisted run_outs", "stumpings", "MVP"],
    "partnerships": ["wicket#", "Partnership", "Balls"],
}


def load(name: str) -> list[dict]:
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype={"match_id": str})
    for col in NUMERIC.get(name, []):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if name == "matches":
        dates = pd.to_datetime(df["date"], errors="coerce")
        df["year"] = dates.dt.year
        df["month"] = dates.dt.month
        df["monthName"] = dates.dt.strftime("%b")
        df["margin_runs"] = df["Win loss Margin"].str.extract(r"(\d+)\s*runs?", expand=False).astype(float)
        df["margin_wickets"] = df["Win loss Margin"].str.extract(r"(\d+)\s*wickets?", expand=False).astype(float)

    return json.loads(df.to_json(orient="records"))


payload = {name: load(name) for name in NUMERIC}
json.dump(payload, sys.stdout)
