---
title: Individual Player Profile
---

<style>
.profile-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  align-items: stretch;
}
@media (max-width: 1000px) { .profile-grid { grid-template-columns: 1fr; } }

.profile-card {
  display: flex;
  flex-direction: column;
  background: var(--ww-panel);
  border: 1px solid var(--ww-border);
  border-top: 3px solid var(--ww-accent);
  border-radius: 12px;
  padding: 0.9rem 1rem 1rem;
}
.profile-card > header {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--ww-muted);
  margin-bottom: 0.8rem;
}

.hero-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.5rem;
  padding-bottom: 0.9rem;
  margin-bottom: 0.8rem;
  border-bottom: 1px solid var(--ww-border);
}
.hero-row .stat { text-align: center; }
.hero-row .stat-value {
  font-size: 1.9rem;
  font-weight: 650;
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: var(--ww-accent);
  font-variant-numeric: tabular-nums;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.85rem 0.5rem;
  margin-top: auto;
}
.stat-grid .stat { text-align: center; }
.stat-value {
  font-size: 1.15rem;
  font-weight: 620;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}
.stat-label {
  margin-top: 0.15rem;
  font-size: 0.62rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ww-muted);
}
.hero-row .stat, .stat-grid .stat { margin: 0; }
.stat > div { margin: 0; }
</style>

<nav class="ww-nav print-hide">
  <a href="./">Season Summary</a>
  <a href="./player" class="active">Individual Player Profile</a>
</nav>

```js
import { aggregateBatting, aggregateBowling, aggregateFielding, formatDate, descending } from "./components/stats.js";
import { kpi, table, num } from "./components/ui.js";

const season = FileAttachment("data/season.json").json();
```

```js
// ---------- field adapter: tolerant of column naming (case / spaces / symbols ignored)
const norm = (s) => String(s).toLowerCase().replace(/[^a-z0-9]/g, "");
const pick = (row, names) => {
  for (const k in row) if (names.includes(norm(k))) return row[k];
  return undefined;
};
const toNum = (v) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
};
const ballsOf = (overs) => {
  const o = toNum(overs);
  return o == null ? null : Math.floor(o) * 6 + Math.round((o - Math.floor(o)) * 10);
};
const fmt = (v, d = 0) => (v == null || v === "" || !Number.isFinite(+v) ? "–" : (+v).toFixed(d));

const DISM = ["howout", "dismissal", "outtype", "out", "wickettype", "dismissaltype", "status"];

function battingInnings(rows, byId) {
  return rows
    .map((r) => {
      const m = byId.get(r.match_id) ?? {};
      const runs = toNum(pick(r, ["runs", "r", "runsscored"]));
      const balls = toNum(pick(r, ["balls", "b", "ballsfaced"]));
      const d = pick(r, DISM);
      const dtxt = d == null ? "" : String(d).trim();
      let notOut;
      if (dtxt !== "") notOut = /not\s*out|^no$/i.test(dtxt);
      else {
        const n = pick(r, ["notout", "no"]);
        notOut = n === true || n === 1 || /^(yes|y|1|true)$/i.test(String(n));
      }
      return {
        match_id: r.match_id,
        date: m.date,
        opposition: m.opposition,
        result: m.result,
        runs,
        balls,
        fours: toNum(pick(r, ["fours", "4s"])) ?? 0,
        sixes: toNum(pick(r, ["sixes", "6s"])) ?? 0,
        sr: balls > 0 ? (runs / balls) * 100 : null,
        notOut,
        dnb: /did\s*not\s*bat|^dnb$|absent/i.test(dtxt),
      };
    })
    .filter((i) => i.runs != null && !i.dnb)
    .sort((a, b) => new Date(a.date) - new Date(b.date))
    .map((i, k) => ({ ...i, n: k + 1, score: `${i.runs}${i.notOut ? "*" : ""}` }));
}

function bowlingInnings(rows, byId) {
  return rows
    .map((r) => {
      const m = byId.get(r.match_id) ?? {};
      const overs = pick(r, ["overs", "o"]);
      const balls = ballsOf(overs);
      const runs = toNum(pick(r, ["runs", "r", "runsconceded"]));
      const wkts = toNum(pick(r, ["wickets", "wkts", "w"])) ?? 0;
      const mdns = toNum(pick(r, ["maidens", "mdns", "m"])) ?? 0;
      return {
        match_id: r.match_id,
        date: m.date,
        opposition: m.opposition,
        result: m.result,
        overs, balls, runs, wkts, mdns,
        econ: balls > 0 && runs != null ? runs / (balls / 6) : null,
        figures: `${overs}-${mdns}-${runs}-${wkts}`,
      };
    })
    .filter((i) => i.balls > 0)
    .sort((a, b) => new Date(a.date) - new Date(b.date))
    .map((i, k) => ({ ...i, n: k + 1 }));
}

// ---------- wicket type (only counts dismissals credited to the bowler)
const classify = (t) => {
  const s = String(t ?? "").trim().toLowerCase();
  if (!s || /run\s*out|retired|obstruct|timed|handled/.test(s)) return null;
  if (/c\s*&\s*b|c\s+and\s+b|caught\s*(and|&)\s*bowled/.test(s)) return "Caught & Bowled";
  if (/lbw|leg\s*before/.test(s)) return "LBW";
  if (/^st\b|stump/.test(s)) return "Stumped";
  if (/hit\s*wicket/.test(s)) return "Hit wicket";
  if (/^c\b|caught/.test(s)) return "Caught";
  if (/^b\b|bowled/.test(s)) return "Bowled";
  return "Other";
};
const TYPE_COLS = { bowled: "Bowled", lbw: "LBW", caught: "Caught", stumped: "Stumped", hitwicket: "Hit wicket", caughtbowled: "Caught & Bowled", candb: "Caught & Bowled" };

function wicketTypes(player, ids, bowlRows) {
  const src = season.wickets ?? season.dismissals;
  const tally = new Map();
  const add = (k, n = 1) => k && n && tally.set(k, (tally.get(k) ?? 0) + n);
  if (Array.isArray(src)) {
    for (const r of src) {
      if (!ids.has(r.match_id)) continue;
      if (pick(r, ["bowler", "bowlername", "player"]) !== player) continue;
      add(classify(pick(r, ["wickettype", "type", "howout", "dismissal", "outtype", "dismissaltype"])));
    }
    return { source: src === season.wickets ? "season.wickets" : "season.dismissals", data: tally };
  }
  let found = false;
  for (const r of bowlRows)
    for (const k in r)
      if (TYPE_COLS[norm(k)]) {
        found = true;
        add(TYPE_COLS[norm(k)], toNum(r[k]) ?? 0);
      }
  return found ? { source: "bowling columns", data: tally } : null;
}
```

```js
// ---------- filter inputs
const allMatches = season.matches;
const seasons = [...new Set(allMatches.map((m) => m.year))].sort((a, b) => b - a);
const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthOptions = monthNames.filter((m) => allMatches.some((row) => row.monthName === m));
const oppositionOptions = [...new Set(allMatches.map((m) => m.opposition))].sort();
const venueOptions = [...new Set(allMatches.map((m) => m.venue))].filter(Boolean).sort();

const playerNames = [...new Set([...season.batting, ...season.bowling, ...season.fielding].map((r) => r.player))]
  .filter(Boolean)
  .sort((a, b) => a.localeCompare(b));

// default player = top run-scorer of the latest season
const latestIds = new Set(allMatches.filter((m) => m.year === seasons[0]).map((m) => m.match_id));
const topBat = aggregateBatting(season.batting.filter((r) => latestIds.has(r.match_id))).sort(descending("Runs"))[0];
const defaultPlayer = topBat?.player ?? playerNames[0];
```

```js
const playerInput = Inputs.select(playerNames, { label: "Player", value: defaultPlayer });
const yearInput = Inputs.select([null, ...seasons], { label: "Season", value: seasons[0], format: (d) => (d == null ? "All seasons" : String(d)) });
const monthsInput = Inputs.checkbox(monthOptions, { label: "Months", value: monthOptions });
const oppositionInput = Inputs.select([null, ...oppositionOptions], { label: "Opposition", format: (d) => d ?? "All" });
const venueInput = Inputs.select([null, ...venueOptions], { label: "Venue", format: (d) => d ?? "All" });
const outcomeInput = Inputs.select([null, "Won", "Lost"], { label: "Result", format: (d) => d ?? "All" });
const inningsInput = Inputs.select([null, "Yes", "No"], {
  label: "Batted",
  format: (d) => (d === null ? "All" : d === "Yes" ? "First" : "Second"),
});

const player = Generators.input(playerInput);
const year = Generators.input(yearInput);
const months = Generators.input(monthsInput);
const opposition = Generators.input(oppositionInput);
const venue = Generators.input(venueInput);
const outcome = Generators.input(outcomeInput);
const innings = Generators.input(inningsInput);
```

```js
// scopeMatches = every filter except season (used for the year-by-year view)
const scopeMatches = allMatches.filter(
  (m) =>
    months.includes(m.monthName) &&
    (!opposition || m.opposition === opposition) &&
    (!venue || m.venue === venue) &&
    (!outcome || m.result === outcome) &&
    (!innings || m.batted_first === innings)
);
const matches = year == null ? scopeMatches : scopeMatches.filter((m) => m.year === year);
const scopeById = new Map(scopeMatches.map((m) => [m.match_id, m]));
const idsSel = new Set(matches.map((m) => m.match_id));

const mine = (rows, ids) => rows.filter((r) => r.player === player && ids.has(r.match_id));
const batRaw = mine(season.batting, idsSel);
const bowlRaw = mine(season.bowling, idsSel);
const fldRaw = mine(season.fielding, idsSel);

const bat = batRaw.length ? aggregateBatting(batRaw)[0] ?? null : null;
const bowl = bowlRaw.length ? aggregateBowling(bowlRaw)[0] ?? null : null;
const fld = fldRaw.length ? aggregateFielding(fldRaw)[0] ?? null : null;

const batInnings = battingInnings(batRaw, scopeById);
const bowlInnings = bowlingInnings(bowlRaw, scopeById);

const playedIds = new Set([...batRaw, ...bowlRaw, ...fldRaw].map((r) => r.match_id));
const playedMatches = matches.filter((m) => playedIds.has(m.match_id));
const wonCount = playedMatches.filter((m) => m.result === "Won").length;
const seasonLabel = year == null ? "All seasons" : String(year);
```

<div class="masthead">
  <div>
    <div class="eyebrow">Individual Player Profile</div>
    <h1>${player}</h1>
  </div>
  <div class="meta">
    ${playedMatches.length} matches · ${seasonLabel}<br>
    <button class="print-hide link-button" onclick="window.print()">Print / Save as PDF</button>
  </div>
</div>

```js
display(
  html`<details class="filter-panel print-hide">
    <summary>Filters <span class="hint">· ${player} · ${seasonLabel}${opposition ? ` · ${opposition}` : ""}${venue ? ` · ${venue}` : ""}${outcome ? ` · ${outcome}` : ""}</span></summary>
    <div class="filter-bar">
      ${[playerInput, yearInput, monthsInput, oppositionInput, venueInput, outcomeInput, inningsInput]}
    </div>
  </details>`
);
```

<div class="section-title"><h2>Career summary</h2><span class="hint">Batting · Bowling · Fielding for the selected filters</span></div>

```js
const stat = (label, value, sub) =>
  html`<div class="stat"><div class="stat-value">${value}</div><div class="stat-label">${label}</div>${sub ? html`<div class="stat-sub">${sub}</div>` : ""}</div>`;

const card = (title, tiles) =>
  html`<section class="profile-card">
    <header>${title}</header>
    ${tiles ? html`<div class="stat-grid">${tiles}</div>` : html`<div class="board-empty">No ${title.toLowerCase()} record for this selection.</div>`}
  </section>`;

const fifties = batInnings.filter((i) => i.runs >= 50 && i.runs < 100).length;
const hundreds = batInnings.filter((i) => i.runs >= 100).length;
const ducks = batInnings.filter((i) => i.runs === 0 && !i.notOut).length;
const hauls = bowlInnings.filter((i) => i.wkts >= 3).length;

const batTiles = bat && [
  stat("Innings", fmt(bat.Inns)),
  stat("Runs", fmt(bat.Runs)),
  stat("High score", bat.HS ?? "–"),
  stat("Average", fmt(bat.Avg, 2)),
  stat("Strike rate", fmt(bat.SR, 1)),
  stat("50s / 100s", `${fifties} / ${hundreds}`),
  stat("Fours", fmt(bat.Fours)),
  stat("Sixes", fmt(bat.Sixes)),
  stat("Balls", fmt(bat.Balls)),
  stat("Not outs", fmt(bat.NO)),
  stat("Ducks", ducks),
  stat("MVP", fmt(bat.MVP, 2)),
];

const bowlTiles = bowl && [
  stat("Innings", fmt(bowl.Inns)),
  stat("Overs", fmt(bowl.Overs, 1)),
  stat("Wickets", fmt(bowl.Wkts)),
  stat("Best", bowl.Best ?? "–"),
  stat("Average", fmt(bowl.Avg, 2)),
  stat("Economy", fmt(bowl.Econ, 2)),
  stat("Strike rate", fmt(bowl.SR, 1)),
  stat("Maidens", fmt(bowl.Mdns)),
  stat("Runs", fmt(bowl.Runs)),
  stat("3+ wkt hauls", hauls),
  stat("MVP", fmt(bowl.MVP, 2)),
];

const fldTiles = fld && [
  stat("Dismissals", fmt(fld.Dismissals)),
  stat("Catches", fmt(fld.Catches)),
  stat("Stumpings", fmt(fld.Stumpings)),
  stat("Run outs", fmt(fld.RunOuts)),
  stat("Assists", fmt(fld.Assists)),
  stat("MVP", fmt(fld.MVP, 2)),
];

display(
  html`<div class="kpi-row" style="margin-bottom:0.75rem">
      ${kpi("Matches", playedMatches.length)}
      ${kpi("Team wins", `${wonCount} / ${playedMatches.length}`, "good")}
      ${kpi("Runs", bat?.Runs ?? 0)}
      ${kpi("Wickets", bowl?.Wkts ?? 0)}
      ${kpi("Dismissals", fld?.Dismissals ?? 0)}
    </div>
    <div class="profile-grid">
      ${card("Batting", batTiles)}
      ${card("Bowling", bowlTiles)}
      ${card("Fielding", fldTiles)}
    </div>`
);
```

<div class="section-title"><h2>Recent form</h2><span class="hint">Last 5 innings</span></div>

```js
const resultPill = (v) => html`<span class="pill ${String(v).toLowerCase()}">${v}</span>`;

const last5Bat = [...batInnings].reverse().slice(0, 5);
const last5Bowl = [...bowlInnings].reverse().slice(0, 5);

display(
  html`<div class="pair-grid">
    <section class="panel">
      <div class="chart-title">Batting</div>
      ${last5Bat.length
        ? table(last5Bat, [
            { key: "date", label: "Date", align: "left", format: formatDate },
            { key: "opposition", label: "Opposition", align: "left" },
            { key: "score", label: "Score" },
            { key: "balls", label: "Balls" },
            { key: "fours", label: "4s" },
            { key: "sixes", label: "6s" },
            { key: "sr", label: "SR", format: num(1) },
            { key: "result", label: "Team", format: resultPill },
          ])
        : html`<div class="board-empty">No batting innings.</div>`}
    </section>
    <section class="panel">
      <div class="chart-title">Bowling</div>
      ${last5Bowl.length
        ? table(last5Bowl, [
            { key: "date", label: "Date", align: "left", format: formatDate },
            { key: "opposition", label: "Opposition", align: "left" },
            { key: "figures", label: "O-M-R-W" },
            { key: "wkts", label: "Wkts" },
            { key: "econ", label: "Econ", format: num(2) },
            { key: "result", label: "Team", format: resultPill },
          ])
        : html`<div class="board-empty">No bowling innings.</div>`}
    </section>
  </div>`
);
```

<div class="section-title"><h2>Batting analysis</h2><span class="hint">Every innings, and how the scores are distributed</span></div>

```js
const N = batInnings.length;
const step = Math.max(1, Math.ceil(N / 14));

const inningsChart = N
  ? resize((width) =>
      Plot.plot({
        width,
        height: 320,
        marginBottom: 58,
        marginLeft: 42,
        x: { type: "band", label: null, tickRotate: -45, tickFormat: (n) => ((n - 1) % step === 0 ? formatDate(batInnings[n - 1].date) : "") },
        y: { label: "Runs", grid: true },
        color: { domain: ["Out", "Not out"], range: ["#1f9d6b", "#d9a441"], legend: true },
        marks: [
          Plot.ruleY([0]),
          Plot.barY(batInnings, {
            x: "n",
            y: "runs",
            fill: (d) => (d.notOut ? "Not out" : "Out"),
            fillOpacity: 0.9,
            tip: true,
            title: (d) => `${formatDate(d.date)} vs ${d.opposition}\n${d.score} off ${d.balls ?? "?"} balls\n4s ${d.fours} · 6s ${d.sixes}`,
          }),
          Number.isFinite(+bat?.Avg) ? Plot.ruleY([+bat.Avg], { stroke: "currentColor", strokeDasharray: "5 4", strokeOpacity: 0.55 }) : null,
        ],
      })
    )
  : html`<div class="board-empty">No batting innings for this selection.</div>`;

const buckets = [
  { label: "0–10", lo: 0, hi: 10 },
  { label: "10–30", lo: 10, hi: 30 },
  { label: "30–50", lo: 30, hi: 50 },
  { label: "50–80", lo: 50, hi: 80 },
  { label: "80–100", lo: 80, hi: 100 },
  { label: "100+", lo: 100, hi: Infinity },
].map((b) => ({ ...b, count: batInnings.filter((i) => i.runs >= b.lo && i.runs < b.hi).length }));

const distChart = N
  ? resize((width) =>
      Plot.plot({
        width,
        height: 320,
        marginBottom: 40,
        x: { label: "Score band", domain: buckets.map((b) => b.label) },
        y: { label: "Innings", grid: true, interval: 1 },
        marks: [
          Plot.ruleY([0]),
          Plot.barY(buckets, { x: "label", y: "count", fill: "#1f9d6b", fillOpacity: 0.9, tip: true }),
          Plot.text(buckets, { x: "label", y: "count", text: "count", dy: -7, fill: "currentColor" }),
        ],
      })
    )
  : html`<div class="board-empty">No batting innings for this selection.</div>`;

display(
  html`<div class="chart-grid">
    <section class="panel">
      <div class="chart-title">Score in every innings <span class="hint">· dashed line = average · gold = not out</span></div>
      ${inningsChart}
    </section>
    <section class="panel">
      <div class="chart-title">Score distribution <span class="hint">· lower bound inclusive</span></div>
      ${distChart}
    </section>
  </div>`
);
```

<div class="section-title"><h2>Bowling analysis</h2><span class="hint">Wickets in every innings, and how they were taken</span></div>

```js
const M = bowlInnings.length;
const bstep = Math.max(1, Math.ceil(M / 14));

const bowlChart = M
  ? resize((width) =>
      Plot.plot({
        width,
        height: 320,
        marginBottom: 58,
        marginLeft: 42,
        x: { type: "band", label: null, tickRotate: -45, tickFormat: (n) => ((n - 1) % bstep === 0 ? formatDate(bowlInnings[n - 1].date) : "") },
        y: { label: "Wickets", grid: true, interval: 1 },
        marks: [
          Plot.ruleY([0]),
          Plot.barY(bowlInnings, {
            x: "n",
            y: "wkts",
            fill: "#1f9d6b",
            fillOpacity: 0.9,
            tip: true,
            title: (d) => `${formatDate(d.date)} vs ${d.opposition}\n${d.figures} (O-M-R-W)\nEcon ${fmt(d.econ, 2)}`,
          }),
        ],
      })
    )
  : html`<div class="board-empty">No bowling innings for this selection.</div>`;




display(
  html`<div class="chart-grid">
    <section class="panel">
      <div class="chart-title">Wickets in every innings</div>
      ${bowlChart}
    </section>
    
  </div>`
);
```

```js
const periodInput = Inputs.radio(["Yearly", "Monthly"], { value: "Yearly" });
const period = Generators.input(periodInput);
```

```js
display(html`<div class="section-title"><h2>Trends</h2><span class="hint">Yearly uses all seasons · Monthly follows the Season filter</span><span style="margin-left:auto" class="print-hide">${periodInput}</span></div>`);
```

```js
const monthKey = (m) => `${m.year}-${String(monthNames.indexOf(m.monthName) + 1).padStart(2, "0")}`;
const groupKey = (m) => (period === "Yearly" ? String(m.year) : monthKey(m));
const groupLabel = (k) => (period === "Yearly" ? k : `${monthNames[+k.slice(5) - 1]} ${k.slice(0, 4)}`);
const periodMatches = period === "Yearly" ? scopeMatches : matches;

const groups = new Map();
for (const m of periodMatches) {
  const k = groupKey(m);
  if (!groups.has(k)) groups.set(k, new Set());
  groups.get(k).add(m.match_id);
}

const allBatP = season.batting.filter((r) => r.player === player);
const allBowlP = season.bowling.filter((r) => r.player === player);
const allFldP = season.fielding.filter((r) => r.player === player);

const trendBat = [];
const trendBowl = [];
for (const k of [...groups.keys()].sort().reverse()) {
  const set = groups.get(k);
  const b = allBatP.filter((r) => set.has(r.match_id));
  const w = allBowlP.filter((r) => set.has(r.match_id));
  const f = allFldP.filter((r) => set.has(r.match_id));
  const mat = new Set([...b, ...w, ...f].map((r) => r.match_id)).size;
  if (b.length) {
    const inn = battingInnings(b, scopeById);
    trendBat.push({
      label: groupLabel(k),
      mat,
      ...aggregateBatting(b)[0],
      fiftyHundred: `${inn.filter((i) => i.runs >= 50 && i.runs < 100).length} / ${inn.filter((i) => i.runs >= 100).length}`,
    });
  }
  if (w.length) trendBowl.push({ label: groupLabel(k), mat, ...aggregateBowling(w)[0] });
}

const periodHead = period === "Yearly" ? "Season" : "Month";

display(
  html`<div class="pair-grid">
    <section class="panel">
      <div class="chart-title">Batting · ${period.toLowerCase()}</div>
      ${trendBat.length
        ? table(trendBat, [
            { key: "label", label: periodHead, align: "left" },
            { key: "mat", label: "Mat" },
            { key: "Inns", label: "Inns" },
            { key: "Runs", label: "Runs" },
            { key: "HS", label: "HS" },
            { key: "Avg", label: "Avg", format: num(2) },
            { key: "SR", label: "SR", format: num(1) },
            { key: "fiftyHundred", label: "50/100" },
            { key: "Fours", label: "4s" },
            { key: "Sixes", label: "6s" },
          ])
        : html`<div class="board-empty">No batting data.</div>`}
    </section>
    <section class="panel">
      <div class="chart-title">Bowling · ${period.toLowerCase()}</div>
      ${trendBowl.length
        ? table(trendBowl, [
            { key: "label", label: periodHead, align: "left" },
            { key: "mat", label: "Mat" },
            { key: "Inns", label: "Inns" },
            { key: "Overs", label: "Overs", format: num(1) },
            { key: "Mdns", label: "Mdns" },
            { key: "Runs", label: "Runs" },
            { key: "Wkts", label: "Wkts" },
            { key: "Best", label: "Best" },
            { key: "Avg", label: "Avg", format: num(2) },
            { key: "Econ", label: "Econ", format: num(2) },
          ])
        : html`<div class="board-empty">No bowling data.</div>`}
    </section>
  </div>`
);
```
