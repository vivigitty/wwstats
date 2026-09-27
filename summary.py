"""Weekend Wickets season dashboard.

    streamlit run summary.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from report import build_pdf

DATA_DIR = Path(__file__).parent / "data"
TEAM = "Weekend Wickets"

st.set_page_config(page_title=f"{TEAM} — Season Summary", page_icon="🏏", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem;}
      [data-testid="stMetricValue"] {font-size: 1.7rem;}
      .record-card {
          background: #11161d; border: 1px solid #263140; border-radius: 10px;
          padding: 0.9rem 1.1rem; height: 100%;
      }
      .record-card .label {color:#8b98a8; font-size:0.78rem; text-transform:uppercase;
          letter-spacing:.06em;}
      .record-card .value {color:#f5f7fa; font-size:1.5rem; font-weight:650; margin:.15rem 0;}
      .record-card .detail {color:#9fb0c4; font-size:0.82rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- data loading


@st.cache_data
def load() -> dict[str, pd.DataFrame]:
    frames = {}
    for name in ("matches", "batting", "bowling", "fielding", "partnerships"):
        path = DATA_DIR / f"{name}.csv"
        frames[name] = pd.read_csv(path, dtype={"match_id": str}) if path.exists() else pd.DataFrame()

    matches = frames["matches"]
    if not matches.empty:
        matches["date"] = pd.to_datetime(matches["date"], errors="coerce")
        matches["year"] = matches["date"].dt.year
        matches["month"] = matches["date"].dt.strftime("%b")
        for col in ("our_runs", "our_wickets", "opp_runs", "opp_wickets", "our_overs", "opp_overs"):
            matches[col] = pd.to_numeric(matches.get(col), errors="coerce")
        matches["margin_runs"] = matches["Win loss Margin"].str.extract(r"(\d+)\s*runs?", expand=False).astype(float)
        matches["margin_wickets"] = matches["Win loss Margin"].str.extract(r"(\d+)\s*wickets?", expand=False).astype(float)
    return frames


def balls(overs: pd.Series) -> pd.Series:
    overs = pd.to_numeric(overs, errors="coerce").fillna(0)
    whole = overs.astype(int)
    return whole * 6 + ((overs - whole) * 10).round().astype(int)


def ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide, leaving NaN wherever the denominator is zero."""
    return numerator / denominator.where(denominator > 0)


def card(label: str, value: str, detail: str = "") -> str:
    return (
        f'<div class="record-card"><div class="label">{label}</div>'
        f'<div class="value">{value}</div><div class="detail">{detail}</div></div>'
    )


def leaderboard(df: pd.DataFrame, value_col: str, fmt: str = "{:g}", top: int = 3) -> pd.DataFrame:
    out = df.head(top).copy()
    out.insert(0, "#", range(1, len(out) + 1))
    out[value_col] = out[value_col].map(lambda v: fmt.format(v))
    return out


def show_board(title: str, caption: str, df: pd.DataFrame) -> None:
    st.markdown(f"**{title}**")
    if df.empty:
        st.caption("No qualifying players")
        return
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption(caption)


def board_grid(boards: list[tuple], per_row: int = 3) -> None:
    for start in range(0, len(boards), per_row):
        cols = st.columns(per_row)
        for col, board in zip(cols, boards[start:start + per_row]):
            with col:
                show_board(*board)


data = load()
matches = data["matches"]

if matches.empty:
    st.error("No data in data/matches.csv. Run `python parse_scorecards.py --all` first.")
    st.stop()


# -------------------------------------------------------------------- filters

st.sidebar.header("Filters")

years = sorted(matches["year"].dropna().unique().astype(int), reverse=True)
year = st.sidebar.selectbox("Season", years, index=0)
season = matches[matches["year"] == year]

month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
available_months = [m for m in month_order if m in set(season["month"])]
months = st.sidebar.multiselect("Months", available_months, default=available_months)

oppositions = st.sidebar.multiselect("Opposition", sorted(season["opposition"].unique()))
venues = st.sidebar.multiselect("Venue", sorted(season["venue"].dropna().unique()))
results = st.sidebar.multiselect("Result", sorted(season["result"].unique()))
batted = st.sidebar.radio("Batted", ["All", "First", "Second"], horizontal=True)

filtered = season[season["month"].isin(months)]
if oppositions:
    filtered = filtered[filtered["opposition"].isin(oppositions)]
if venues:
    filtered = filtered[filtered["venue"].isin(venues)]
if results:
    filtered = filtered[filtered["result"].isin(results)]
if batted != "All":
    filtered = filtered[filtered["batted_first"] == ("Yes" if batted == "First" else "No")]

ids = set(filtered["match_id"])
batting = data["batting"][data["batting"]["match_id"].isin(ids)]
bowling = data["bowling"][data["bowling"]["match_id"].isin(ids)]
fielding = data["fielding"][data["fielding"]["match_id"].isin(ids)]
partnerships = data["partnerships"][data["partnerships"]["match_id"].isin(ids)]

st.sidebar.markdown("---")
min_inns = st.sidebar.slider("Min innings for rate-based boards", 1, 10, 3)

st.title(f"{TEAM} — {year} Season Summary")
if filtered.empty:
    st.warning("No matches match the current filters.")
    st.stop()

span = f"{filtered['date'].min():%d %b} – {filtered['date'].max():%d %b %Y}"
st.caption(f"{len(filtered)} matches · {span}")


# -------------------------------------------------------------------- headline

played = len(filtered)
won = int((filtered["result"] == "Won").sum())
lost = int((filtered["result"] == "Lost").sum())
other = played - won - lost

c = st.columns(5)
c[0].metric("Played", played)
c[1].metric("Won", won)
c[2].metric("Lost", lost)
c[3].metric("Win %", f"{won / played * 100:.1f}%")
c[4].metric("Other", other)

st.markdown("### Season records")

wins = filtered[filtered["result"] == "Won"]
defended = wins[wins["batted_first"] == "Yes"]
chased = wins[wins["batted_first"] == "No"]


def best(df: pd.DataFrame, col: str, largest: bool = True):
    df = df.dropna(subset=[col])
    if df.empty:
        return None
    return df.loc[df[col].idxmax() if largest else df[col].idxmin()]


records = []

row = best(wins, "margin_runs")
records.append(("Biggest win (runs)", f"{row['margin_runs']:.0f} runs", f"vs {row['opposition']} · {row['date']:%d %b}") if row is not None else ("Biggest win (runs)", "—", ""))

row = best(wins, "margin_wickets")
records.append(("Biggest win (wickets)", f"{row['margin_wickets']:.0f} wickets", f"vs {row['opposition']} · {row['date']:%d %b}") if row is not None else ("Biggest win (wickets)", "—", ""))

row = best(filtered, "our_runs")
records.append(("Highest total", f"{row['our_runs']:.0f}/{row['our_wickets']:.0f}", f"vs {row['opposition']} · {row['our_overs']} ov") if row is not None else ("Highest total", "—", ""))

row = best(filtered, "our_runs", largest=False)
records.append(("Lowest total", f"{row['our_runs']:.0f}/{row['our_wickets']:.0f}", f"vs {row['opposition']} · {row['our_overs']} ov") if row is not None else ("Lowest total", "—", ""))

row = best(defended, "our_runs", largest=False)
records.append(("Best defended score", f"{row['our_runs']:.0f}", f"vs {row['opposition']} · won by {row['margin_runs']:.0f} runs") if row is not None else ("Best defended score", "—", "No wins batting first"))

row = best(chased, "opp_runs")
records.append(("Biggest chase", f"{row['opp_runs'] + 1:.0f}", f"vs {row['opposition']} · {row['our_overs']} ov") if row is not None else ("Biggest chase", "—", "No wins chasing"))

cols = st.columns(3)
for i, (label, value, detail) in enumerate(records):
    cols[i % 3].markdown(card(label, value, detail), unsafe_allow_html=True)

st.markdown("")

pdf_sections: list[tuple[str, list]] = []


# -------------------------------------------------------------------- batting

st.markdown("## 🏏 Batting")

if batting.empty:
    st.caption("No batting data")
else:
    bat = batting.copy()
    bat["not_out"] = bat["Dismissal Type"].eq("Not Out")
    agg = bat.groupby("player").agg(
        Inns=("runs", "size"),
        Runs=("runs", "sum"),
        Balls=("balls", "sum"),
        NO=("not_out", "sum"),
        Fours=("fours", "sum"),
        Sixes=("sixes", "sum"),
        HS=("runs", "max"),
        MVP=("MVP", "sum"),
    ).reset_index()
    agg["Outs"] = agg["Inns"] - agg["NO"]
    agg["Avg"] = ratio(agg["Runs"], agg["Outs"]).round(2)
    agg["SR"] = (ratio(agg["Runs"], agg["Balls"]) * 100).round(2)
    rated = agg[agg["Inns"] >= min_inns]

    bat_boards = [
        ("Most runs", "Runs scored", leaderboard(agg.sort_values("Runs", ascending=False)[["player", "Runs", "Inns"]], "Runs")),
        ("Most fours", "Boundaries hit", leaderboard(agg.sort_values("Fours", ascending=False)[["player", "Fours", "Runs"]], "Fours")),
        ("Most sixes", "Maximums hit", leaderboard(agg.sort_values("Sixes", ascending=False)[["player", "Sixes", "Runs"]], "Sixes")),
        ("Best strike rate", f"Min {min_inns} innings", leaderboard(rated.sort_values("SR", ascending=False)[["player", "SR", "Runs"]], "SR", "{:.2f}")),
        ("Best average", f"Min {min_inns} innings", leaderboard(rated.dropna(subset=["Avg"]).sort_values("Avg", ascending=False)[["player", "Avg", "Runs"]], "Avg", "{:.2f}")),
    ]
    board_grid(bat_boards)
    pdf_sections.append(("Batting", [(t, d) for t, _, d in bat_boards]))

    with st.expander("Full batting table"):
        st.dataframe(
            agg[["player", "Inns", "Runs", "Balls", "NO", "HS", "Avg", "SR", "Fours", "Sixes", "MVP"]]
            .sort_values("Runs", ascending=False),
            hide_index=True, use_container_width=True,
        )


# -------------------------------------------------------------------- bowling

st.markdown("## 🎯 Bowling")

if bowling.empty:
    st.caption("No bowling data")
else:
    bowl = bowling.copy()
    bowl["balls"] = balls(bowl["overs"])
    agg = bowl.groupby("player").agg(
        Inns=("wickets", "size"),
        Wkts=("wickets", "sum"),
        Runs=("runs", "sum"),
        Balls=("balls", "sum"),
        Mdns=("maidens", "sum"),
        Best=("wickets", "max"),
        MVP=("MVP", "sum"),
    ).reset_index()
    agg["Econ"] = ratio(agg["Runs"], agg["Balls"] / 6).round(2)
    agg["Avg"] = ratio(agg["Runs"], agg["Wkts"]).round(2)
    agg["SR"] = ratio(agg["Balls"], agg["Wkts"]).round(2)
    rated = agg[agg["Inns"] >= min_inns]

    bowl_boards = [
        ("Most wickets", "Wickets taken", leaderboard(agg.sort_values(["Wkts", "Econ"], ascending=[False, True])[["player", "Wkts", "Inns"]], "Wkts")),
        ("Best economy", f"Runs per over · min {min_inns} innings", leaderboard(rated.dropna(subset=["Econ"]).sort_values("Econ")[["player", "Econ", "Wkts"]], "Econ", "{:.2f}")),
        ("Best strike rate", f"Balls per wicket · min {min_inns} innings", leaderboard(rated.dropna(subset=["SR"]).sort_values("SR")[["player", "SR", "Wkts"]], "SR", "{:.1f}")),
        ("Best average", f"Runs per wicket · min {min_inns} innings", leaderboard(rated.dropna(subset=["Avg"]).sort_values("Avg")[["player", "Avg", "Wkts"]], "Avg", "{:.2f}")),
    ]
    board_grid(bowl_boards)
    pdf_sections.append(("Bowling", [(t, d) for t, _, d in bowl_boards]))

    with st.expander("Full bowling table"):
        st.dataframe(
            agg[["player", "Inns", "Balls", "Mdns", "Runs", "Wkts", "Best", "Avg", "Econ", "SR", "MVP"]]
            .sort_values("Wkts", ascending=False),
            hide_index=True, use_container_width=True,
        )


# ------------------------------------------------------------------- fielding

st.markdown("## 🧤 Fielding")

if fielding.empty:
    st.caption("No fielding data")
else:
    field = fielding.groupby("player").agg(
        Catches=("catches", "sum"),
        RunOuts=("run_outs", "sum"),
        Assists=("assisted run_outs", "sum"),
        Stumpings=("stumpings", "sum"),
        MVP=("MVP", "sum"),
    ).reset_index()
    field["Dismissals"] = field["Catches"] + field["RunOuts"] + field["Assists"] + field["Stumpings"]

    cols = st.columns([1, 2])
    with cols[0]:
        field_board = leaderboard(field.sort_values("Dismissals", ascending=False)[["player", "Dismissals", "Catches"]], "Dismissals")
        show_board("Most dismissals", "Catches + run outs + assists + stumpings", field_board)
        pdf_sections.append(("Fielding", [("Most dismissals", field_board)]))
    with cols[1]:
        st.markdown("**All fielders**")
        st.dataframe(
            field[["player", "Catches", "Stumpings", "RunOuts", "Assists", "Dismissals", "MVP"]]
            .sort_values("Dismissals", ascending=False),
            hide_index=True, use_container_width=True,
        )


# --------------------------------------------------------------- partnerships

st.markdown("## 🤝 Partnerships")

if partnerships.empty:
    st.caption("No partnership data")
else:
    pairs = partnerships.merge(filtered[["match_id", "opposition", "date"]], on="match_id", how="left")
    pairs["Pair"] = pairs.apply(
        lambda r: " & ".join(sorted([str(r["player1_name"]), str(r["player2_name"])])), axis=1
    )

    best_stands = pairs.sort_values("Partnership", ascending=False).head(3).copy()
    best_stands["Stand"] = best_stands.apply(
        lambda r: f"{r['Partnership']:.0f}{'*' if r['Unbeaten'] == 'Yes' else ''} ({r['Balls']:.0f}b)", axis=1
    )
    best_stands["Match"] = best_stands.apply(lambda r: f"vs {r['opposition']} · {r['date']:%d %b}", axis=1)
    best_stands.insert(0, "#", range(1, len(best_stands) + 1))

    by_player = pd.concat([
        pairs[["player1_name", "Partnership"]].rename(columns={"player1_name": "player"}),
        pairs[["player2_name", "Partnership"]].rename(columns={"player2_name": "player"}),
    ])
    by_player = by_player[by_player["player"].astype(str).str.strip() != ""]
    totals = by_player.groupby("player").agg(
        Runs=("Partnership", "sum"), Stands=("Partnership", "size")
    ).reset_index().sort_values("Runs", ascending=False)

    pair_totals = pairs.groupby("Pair").agg(
        Runs=("Partnership", "sum"), Stands=("Partnership", "size"), Best=("Partnership", "max")
    ).reset_index().sort_values("Runs", ascending=False)

    cols = st.columns(3)
    stands_board = best_stands[["#", "Pair", "Stand", "Match"]]
    runs_board = leaderboard(totals[["player", "Runs", "Stands"]], "Runs")
    pairs_board = leaderboard(pair_totals[["Pair", "Runs", "Stands"]], "Runs")
    with cols[0]:
        st.markdown("**Highest partnerships**")
        st.dataframe(stands_board, hide_index=True, use_container_width=True)
        st.caption("* denotes unbroken")
    with cols[1]:
        show_board("Most partnership runs", "Total runs added while at the crease", runs_board)
    with cols[2]:
        show_board("Best partners", "Most runs added together", pairs_board)

    pdf_sections.append((
        "Partnerships",
        [
            ("Highest partnerships (* unbroken)", stands_board[["#", "Pair", "Stand"]]),
            ("Most partnership runs", runs_board),
            ("Best partners", pairs_board),
        ],
    ))

    with st.expander("All partnerships"):
        st.dataframe(
            pairs[["date", "opposition", "wicket#", "Pair", "Partnership", "Balls", "Unbeaten"]]
            .sort_values("Partnership", ascending=False),
            hide_index=True, use_container_width=True,
        )


# --------------------------------------------------------------- match results

st.markdown("## 📋 Results")
results_table = (
    filtered[["date", "opposition", "venue", "batted_first", "our_runs", "our_wickets",
              "opp_runs", "opp_wickets", "result", "Win loss Margin", "captain"]]
    .sort_values("date", ascending=False)
    .rename(columns={
        "date": "Date", "opposition": "Opposition", "venue": "Venue",
        "batted_first": "Batted 1st", "our_runs": "Our runs", "our_wickets": "Our wkts",
        "opp_runs": "Opp runs", "opp_wickets": "Opp wkts", "result": "Result",
        "Win loss Margin": "Margin", "captain": "Captain",
    })
)
st.dataframe(results_table, hide_index=True, use_container_width=True)


# ------------------------------------------------------------------ pdf export

pdf_results = results_table.copy()
pdf_results["Date"] = pdf_results["Date"].dt.strftime("%d %b")
for col in ("Our runs", "Our wkts", "Opp runs", "Opp wkts"):
    pdf_results[col] = pdf_results[col].fillna(0).astype(int)

pdf_bytes = build_pdf({
    "title": f"{TEAM} — {year} Season Summary",
    "subtitle": f"{len(filtered)} matches · {span}" + (f" · {', '.join(oppositions)}" if oppositions else ""),
    "headline": [
        ("Played", played), ("Won", won), ("Lost", lost),
        ("Win %", f"{won / played * 100:.1f}%"), ("Other", other),
    ],
    "records": records,
    "sections": pdf_sections,
    "results": pdf_results,
})

st.sidebar.markdown("---")
st.sidebar.download_button(
    "📄 Download PDF report",
    data=pdf_bytes,
    file_name=f"{TEAM.replace(' ', '_')}_{year}_Summary.pdf",
    mime="application/pdf",
    use_container_width=True,
)

st.markdown("---")
st.download_button(
    "📄 Download this summary as PDF",
    data=pdf_bytes,
    file_name=f"{TEAM.replace(' ', '_')}_{year}_Summary.pdf",
    mime="application/pdf",
)
st.caption("The PDF reflects the filters currently applied.")
