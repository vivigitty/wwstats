// Aggregations for the season dashboard. Mirrors the logic in parse_scorecards.py.

export const ratio = (numerator, denominator) =>
  denominator > 0 ? numerator / denominator : null;

export const sum = (rows, key) => rows.reduce((total, r) => total + (+r[key] || 0), 0);

/** "4.4" overs -> 28 balls. */
export function ballsFromOvers(overs) {
  const value = +overs || 0;
  const whole = Math.floor(value);
  return whole * 6 + Math.round((value - whole) * 10);
}

function groupBy(rows, key) {
  const groups = new Map();
  for (const row of rows) {
    const name = (row[key] ?? "").toString().trim();
    if (!name) continue;
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(row);
  }
  return groups;
}

export function aggregateBatting(rows) {
  return [...groupBy(rows, "player")].map(([player, inns]) => {
    const notOuts = inns.filter((r) => r["Dismissal Type"] === "Not Out").length;
    const runs = sum(inns, "runs");
    const balls = sum(inns, "balls");
    const outs = inns.length - notOuts;
    return {
      player,
      Inns: inns.length,
      Runs: runs,
      Balls: balls,
      NO: notOuts,
      HS: Math.max(...inns.map((r) => +r.runs || 0)),
      Fours: sum(inns, "fours"),
      Sixes: sum(inns, "sixes"),
      MVP: +sum(inns, "MVP").toFixed(2),
      Avg: ratio(runs, outs),
      SR: ratio(runs, balls) * 100 || null,
    };
  });
}

export function aggregateBowling(rows) {
  return [...groupBy(rows, "player")].map(([player, spells]) => {
    const balls = spells.reduce((total, r) => total + ballsFromOvers(r.overs), 0);
    const runs = sum(spells, "runs");
    const wickets = sum(spells, "wickets");
    return {
      player,
      Inns: spells.length,
      Balls: balls,
      Overs: +(Math.floor(balls / 6) + (balls % 6) / 10).toFixed(1),
      Mdns: sum(spells, "maidens"),
      Runs: runs,
      Wkts: wickets,
      Best: Math.max(...spells.map((r) => +r.wickets || 0)),
      MVP: +sum(spells, "MVP").toFixed(2),
      Econ: ratio(runs, balls / 6),
      Avg: ratio(runs, wickets),
      SR: ratio(balls, wickets),
    };
  });
}

export function aggregateFielding(rows) {
  return [...groupBy(rows, "player")].map(([player, games]) => {
    const catches = sum(games, "catches");
    const runOuts = sum(games, "run_outs");
    const assists = sum(games, "assisted run_outs");
    const stumpings = sum(games, "stumpings");
    return {
      player,
      Catches: catches,
      Stumpings: stumpings,
      RunOuts: runOuts,
      Assists: assists,
      Dismissals: catches + runOuts + assists + stumpings,
      MVP: +sum(games, "MVP").toFixed(2),
    };
  });
}

export function partnershipViews(rows, matchesById) {
  const enriched = rows.map((r) => ({
    ...r,
    opposition: matchesById.get(r.match_id)?.opposition ?? "",
    date: matchesById.get(r.match_id)?.date ?? "",
    Pair: [r.player1_name, r.player2_name]
      .map((p) => (p ?? "").toString().trim())
      .filter(Boolean)
      .sort()
      .join(" & "),
  }));

  const byPlayer = new Map();
  for (const stand of enriched) {
    for (const name of [stand.player1_name, stand.player2_name]) {
      const player = (name ?? "").toString().trim();
      if (!player) continue;
      const current = byPlayer.get(player) ?? { player, Runs: 0, Stands: 0 };
      current.Runs += +stand.Partnership || 0;
      current.Stands += 1;
      byPlayer.set(player, current);
    }
  }

  const byPair = new Map();
  for (const stand of enriched) {
    if (!stand.Pair) continue;
    const current = byPair.get(stand.Pair) ?? { Pair: stand.Pair, Runs: 0, Stands: 0, Best: 0 };
    current.Runs += +stand.Partnership || 0;
    current.Stands += 1;
    current.Best = Math.max(current.Best, +stand.Partnership || 0);
    byPair.set(stand.Pair, current);
  }

  return {
    stands: enriched,
    byPlayer: [...byPlayer.values()],
    byPair: [...byPair.values()],
  };
}

const pick = (rows, key, largest = true) => {
  const valid = rows.filter((r) => r[key] != null && !Number.isNaN(+r[key]));
  if (!valid.length) return null;
  return valid.reduce((best, row) => ((largest ? +row[key] > +best[key] : +row[key] < +best[key]) ? row : best));
};

export function seasonRecords(matches) {
  const wins = matches.filter((m) => m.result === "Won");
  const defended = wins.filter((m) => m.batted_first === "Yes");
  const chased = wins.filter((m) => m.batted_first === "No");
  const when = (m) => `vs ${m.opposition} · ${formatDate(m.date)}`;

  const rows = [
    ["Biggest win (runs)", pick(wins, "margin_runs"), (m) => `${m.margin_runs} runs`, when],
    ["Biggest win (wickets)", pick(wins, "margin_wickets"), (m) => `${m.margin_wickets} wickets`, when],
    ["Highest total", pick(matches, "our_runs"), (m) => `${m.our_runs}/${m.our_wickets}`, (m) => `vs ${m.opposition} · ${m.our_overs} ov`],
    ["Lowest total", pick(matches, "our_runs", false), (m) => `${m.our_runs}/${m.our_wickets}`, (m) => `vs ${m.opposition} · ${m.our_overs} ov`],
    ["Best defended score", pick(defended, "our_runs", false), (m) => `${m.our_runs}`, (m) => `vs ${m.opposition} · won by ${m.margin_runs} runs`],
    ["Biggest chase", pick(chased, "opp_runs"), (m) => `${m.opp_runs + 1}`, (m) => `vs ${m.opposition} · ${m.our_overs} ov`],
  ];

  return rows.map(([label, match, value, detail]) => ({
    label,
    value: match ? value(match) : "—",
    detail: match ? detail(match) : "No qualifying match",
  }));
}

export function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(+date)
    ? String(value)
    : date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export const descending = (key) => (a, b) => (+b[key] || 0) - (+a[key] || 0);
export const ascending = (key) => (a, b) => (+a[key] || Infinity) - (+b[key] || Infinity);
