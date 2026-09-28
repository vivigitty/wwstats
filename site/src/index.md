---
title: Season Summary
---

```js
import {
  aggregateBatting,
  aggregateBowling,
  aggregateFielding,
  partnershipViews,
  seasonRecords,
  formatDate,
  descending,
  ascending,
} from "./components/stats.js";
import { kpi, record, board, table, num, int } from "./components/ui.js";

const season = FileAttachment("data/season.json").json();
```

```js
const allMatches = season.matches;
const seasons = [...new Set(allMatches.map((m) => m.year))].sort((a, b) => b - a);
const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthOptions = monthNames.filter((m) => allMatches.some((row) => row.monthName === m));
const oppositionOptions = [...new Set(allMatches.map((m) => m.opposition))].sort();
const venueOptions = [...new Set(allMatches.map((m) => m.venue))].filter(Boolean).sort();
```

```js
const yearInput = Inputs.select(seasons, { label: "Season", value: seasons[0], format: (d) => String(d) });
const monthsInput = Inputs.checkbox(monthOptions, { label: "Months", value: monthOptions });
const oppositionInput = Inputs.select([null, ...oppositionOptions], { label: "Opposition", format: (d) => d ?? "All" });
const venueInput = Inputs.select([null, ...venueOptions], { label: "Venue", format: (d) => d ?? "All" });
const outcomeInput = Inputs.select([null, "Won", "Lost"], { label: "Result", format: (d) => d ?? "All" });
const inningsInput = Inputs.select([null, "Yes", "No"], {
  label: "Batted",
  format: (d) => (d === null ? "All" : d === "Yes" ? "First" : "Second"),
});
const minInnsInput = Inputs.range([1, 10], { label: "Min innings", step: 1, value: 3 });

const year = Generators.input(yearInput);
const months = Generators.input(monthsInput);
const opposition = Generators.input(oppositionInput);
const venue = Generators.input(venueInput);
const outcome = Generators.input(outcomeInput);
const innings = Generators.input(inningsInput);
const minInns = Generators.input(minInnsInput);
```

```js
const matches = allMatches.filter(
  (m) =>
    m.year === year &&
    months.includes(m.monthName) &&
    (!opposition || m.opposition === opposition) &&
    (!venue || m.venue === venue) &&
    (!outcome || m.result === outcome) &&
    (!innings || m.batted_first === innings)
);

const ids = new Set(matches.map((m) => m.match_id));
const matchesById = new Map(matches.map((m) => [m.match_id, m]));
const keep = (rows) => rows.filter((r) => ids.has(r.match_id));

const batting = aggregateBatting(keep(season.batting));
const bowling = aggregateBowling(keep(season.bowling));
const fielding = aggregateFielding(keep(season.fielding));
const partnerships = partnershipViews(keep(season.partnerships), matchesById);

const played = matches.length;
const won = matches.filter((m) => m.result === "Won").length;
const lost = matches.filter((m) => m.result === "Lost").length;
const winPct = played ? (won / played) * 100 : 0;
const span = played
  ? `${formatDate(matches.reduce((a, b) => (a.date < b.date ? a : b)).date)} – ${formatDate(
      matches.reduce((a, b) => (a.date > b.date ? a : b)).date
    )} ${year}`
  : "No matches in range";
```

<div class="masthead">
  <div>
    <div class="eyebrow">Weekend Wickets</div>
    <h1>${year} Season Summary</h1>
  </div>
  <div class="meta">
    ${played} matches · ${span}<br>
    <button class="print-hide link-button" onclick="window.print()">Print / Save as PDF</button>
  </div>
</div>

```js
display(
  html`<div class="filter-bar print-hide">
    ${[yearInput, monthsInput, oppositionInput, venueInput, outcomeInput, inningsInput, minInnsInput]}
  </div>`
);
```

```js
display(
  html`<div class="kpi-row">
    ${kpi("Played", played)}
    ${kpi("Won", won, "good")}
    ${kpi("Lost", lost, "bad")}
    ${kpi("Win %", `${winPct.toFixed(1)}%`)}
    ${kpi("Runs scored", batting.reduce((t, r) => t + r.Runs, 0))}
    ${kpi("Wickets taken", bowling.reduce((t, r) => t + r.Wkts, 0))}
  </div>`
);
```

<div class="section-title"><h2>Season records</h2></div>

```js
display(html`<div class="record-grid">${seasonRecords(matches).map(record)}</div>`);
```

<div class="section-title">
  <h2>Form</h2>
  <span class="hint">Bars are our score · dots are the opposition</span>
</div>

```js
const timeline = [...matches].sort((a, b) => new Date(a.date) - new Date(b.date));

display(
  Plot.plot({
    height: 280,
    marginLeft: 45,
    marginBottom: 52,
    x: { label: null, type: "band", tickFormat: formatDate, tickRotate: -45 },
    y: { label: "Runs", grid: true },
    color: { domain: ["Won", "Lost"], range: ["#1f9d6b", "#c2503f"], legend: true },
    marks: [
      Plot.ruleY([0]),
      Plot.barY(timeline, {
        x: "date",
        y: "our_runs",
        fill: "result",
        fillOpacity: 0.85,
        tip: true,
        title: (d) =>
          `${formatDate(d.date)} vs ${d.opposition}\nUs ${d.our_runs}/${d.our_wickets} · Them ${d.opp_runs}/${d.opp_wickets}\n${d.result} by ${d["Win loss Margin"]}`,
      }),
      Plot.dot(timeline, { x: "date", y: "opp_runs", r: 3.5, fill: "currentColor" }),
    ],
  })
);
```

<div class="section-title">
  <h2>Batting</h2>
  <span class="hint">Rate boards need ${minInns}+ innings</span>
</div>

```js
const battingRated = batting.filter((r) => r.Inns >= minInns);

display(
  html`<div class="board-grid">
    ${board({
      title: "Most runs",
      rows: [...batting].sort(descending("Runs")),
      nameKey: "player",
      columns: [
        { key: "Runs", format: int },
        { key: "Inns", label: "innings", format: int },
      ],
    })}
    ${board({
      title: "Most fours",
      rows: [...batting].sort(descending("Fours")),
      nameKey: "player",
      columns: [
        { key: "Fours", format: int },
        { key: "Runs", label: "runs", format: int },
      ],
    })}
    ${board({
      title: "Most sixes",
      rows: [...batting].sort(descending("Sixes")),
      nameKey: "player",
      columns: [
        { key: "Sixes", format: int },
        { key: "Runs", label: "runs", format: int },
      ],
    })}
    ${board({
      title: "Best strike rate",
      note: `Minimum ${minInns} innings`,
      rows: [...battingRated].sort(descending("SR")),
      nameKey: "player",
      columns: [
        { key: "SR", format: num(1) },
        { key: "Runs", label: "runs", format: int },
      ],
    })}
    ${board({
      title: "Best average",
      note: `Minimum ${minInns} innings · not-outs excluded`,
      rows: battingRated.filter((r) => r.Avg != null).sort(descending("Avg")),
      nameKey: "player",
      columns: [
        { key: "Avg", format: num(2) },
        { key: "Runs", label: "runs", format: int },
      ],
    })}
  </div>`
);
```

<details class="print-hide"><summary>Full batting table</summary>

```js
display(
  table([...batting].sort(descending("Runs")), [
    { key: "player", label: "Player", align: "left" },
    { key: "Inns", label: "Inns" },
    { key: "Runs", label: "Runs" },
    { key: "Balls", label: "Balls" },
    { key: "NO", label: "NO" },
    { key: "HS", label: "HS" },
    { key: "Avg", label: "Avg", format: num(2) },
    { key: "SR", label: "SR", format: num(1) },
    { key: "Fours", label: "4s" },
    { key: "Sixes", label: "6s" },
    { key: "MVP", label: "MVP", format: num(2) },
  ])
);
```

</details>

<div class="section-title">
  <h2>Bowling</h2>
  <span class="hint">Rate boards need ${minInns}+ innings</span>
</div>

```js
const bowlingRated = bowling.filter((r) => r.Inns >= minInns);

display(
  html`<div class="board-grid">
    ${board({
      title: "Most wickets",
      rows: [...bowling].sort(descending("Wkts")),
      nameKey: "player",
      columns: [
        { key: "Wkts", format: int },
        { key: "Inns", label: "innings", format: int },
      ],
    })}
    ${board({
      title: "Best economy",
      note: `Runs per over · minimum ${minInns} innings`,
      rows: bowlingRated.filter((r) => r.Econ != null).sort(ascending("Econ")),
      nameKey: "player",
      columns: [
        { key: "Econ", format: num(2) },
        { key: "Wkts", label: "wickets", format: int },
      ],
    })}
    ${board({
      title: "Best strike rate",
      note: `Balls per wicket · minimum ${minInns} innings`,
      rows: bowlingRated.filter((r) => r.SR != null).sort(ascending("SR")),
      nameKey: "player",
      columns: [
        { key: "SR", format: num(1) },
        { key: "Wkts", label: "wickets", format: int },
      ],
    })}
    ${board({
      title: "Best average",
      note: `Runs per wicket · minimum ${minInns} innings`,
      rows: bowlingRated.filter((r) => r.Avg != null).sort(ascending("Avg")),
      nameKey: "player",
      columns: [
        { key: "Avg", format: num(2) },
        { key: "Wkts", label: "wickets", format: int },
      ],
    })}
  </div>`
);
```

<details class="print-hide"><summary>Full bowling table</summary>

```js
display(
  table([...bowling].sort(descending("Wkts")), [
    { key: "player", label: "Player", align: "left" },
    { key: "Inns", label: "Inns" },
    { key: "Overs", label: "Overs", format: num(1) },
    { key: "Mdns", label: "Mdns" },
    { key: "Runs", label: "Runs" },
    { key: "Wkts", label: "Wkts" },
    { key: "Best", label: "Best" },
    { key: "Avg", label: "Avg", format: num(2) },
    { key: "Econ", label: "Econ", format: num(2) },
    { key: "SR", label: "SR", format: num(1) },
    { key: "MVP", label: "MVP", format: num(2) },
  ])
);
```

</details>

<div class="section-title">
  <h2>Fielding</h2>
  <span class="hint">Catches + stumpings + run outs + assists</span>
</div>

```js
display(
  html`<div class="board-grid" style="grid-template-columns: minmax(240px, 1fr) 2.2fr;">
    ${board({
      title: "Most dismissals",
      rows: [...fielding].sort(descending("Dismissals")),
      nameKey: "player",
      columns: [
        { key: "Dismissals", format: int },
        { key: "Catches", label: "catches", format: int },
      ],
    })}
    ${table([...fielding].sort(descending("Dismissals")), [
      { key: "player", label: "Player", align: "left" },
      { key: "Catches", label: "Ct" },
      { key: "Stumpings", label: "St" },
      { key: "RunOuts", label: "RO" },
      { key: "Assists", label: "Assists" },
      { key: "Dismissals", label: "Total" },
      { key: "MVP", label: "MVP", format: num(2) },
    ])}
  </div>`
);
```

<div class="section-title">
  <h2>Partnerships</h2>
  <span class="hint">* denotes an unbroken stand</span>
</div>

```js
const topStands = [...partnerships.stands].sort(descending("Partnership")).map((s) => ({
  ...s,
  stand: `${s.Partnership}${s.Unbeaten === "Yes" ? "*" : ""}`,
  context: `${s.Balls} balls · vs ${s.opposition}`,
}));

display(
  html`<div class="board-grid">
    ${board({
      title: "Highest partnerships",
      rows: topStands,
      nameKey: "Pair",
      columns: [
        { key: "stand", format: (v) => v },
        { key: "context", label: "", format: (v) => v },
      ],
    })}
    ${board({
      title: "Most partnership runs",
      note: "Runs added while at the crease",
      rows: [...partnerships.byPlayer].sort(descending("Runs")),
      nameKey: "player",
      columns: [
        { key: "Runs", format: int },
        { key: "Stands", label: "stands", format: int },
      ],
    })}
    ${board({
      title: "Best partners",
      note: "Most runs added together",
      rows: [...partnerships.byPair].sort(descending("Runs")),
      nameKey: "Pair",
      columns: [
        { key: "Runs", format: int },
        { key: "Stands", label: "stands", format: int },
      ],
    })}
  </div>`
);
```

<details class="print-hide"><summary>All partnerships</summary>

```js
display(
  table([...partnerships.stands].sort(descending("Partnership")), [
    { key: "date", label: "Date", align: "left", format: formatDate },
    { key: "opposition", label: "Opposition", align: "left" },
    { key: "wicket#", label: "Wkt" },
    { key: "Pair", label: "Partnership", align: "left" },
    { key: "Partnership", label: "Runs" },
    { key: "Balls", label: "Balls" },
    { key: "Unbeaten", label: "Unbeaten" },
  ])
);
```

</details>

<div class="section-title"><h2>Results</h2></div>

```js
display(
  table(
    [...matches].sort((a, b) => new Date(b.date) - new Date(a.date)),
    [
      { key: "date", label: "Date", align: "left", format: formatDate },
      { key: "opposition", label: "Opposition", align: "left" },
      { key: "venue", label: "Venue", align: "left" },
      { key: "batted_first", label: "Batted", format: (v) => (v === "Yes" ? "1st" : "2nd") },
      { key: "our_runs", label: "Us", format: (v, r) => `${v}/${r.our_wickets}` },
      { key: "opp_runs", label: "Them", format: (v, r) => `${v}/${r.opp_wickets}` },
      {
        key: "result",
        label: "Result",
        format: (v) => html`<span class="pill ${String(v).toLowerCase()}">${v}</span>`,
      },
      { key: "Win loss Margin", label: "Margin", align: "left" },
      { key: "captain", label: "Captain", align: "left" },
    ]
  )
);
```
