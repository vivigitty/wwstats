import { html } from "npm:htl";

export function kpi(label, value, tone = "") {
  return html`<div class="kpi ${tone}">
    <div class="kpi-value">${value}</div>
    <div class="kpi-label">${label}</div>
  </div>`;
}

export function record({ label, value, detail }) {
  return html`<div class="record">
    <div class="record-label">${label}</div>
    <div class="record-value">${value}</div>
    <div class="record-detail">${detail}</div>
  </div>`;
}

const RANK = ["gold", "silver", "bronze"];

/**
 * A podium-style top-N board.
 * columns: [{key, label, format}] — the first is the headline metric.
 */
export function board({ title, note, rows, nameKey, columns, top = 3 }) {
  const shown = rows.slice(0, top);
  return html`<div class="board">
    <div class="board-title">${title}</div>
    ${
      shown.length === 0
        ? html`<div class="board-empty">No qualifying players</div>`
        : html`<ol class="board-list">
            ${shown.map(
              (row, i) => html`<li class="board-row ${RANK[i] ?? ""}">
                <span class="board-rank">${i + 1}</span>
                <span class="board-name">${row[nameKey]}</span>
                <span class="board-metric">${columns[0].format(row[columns[0].key])}</span>
                ${
                  columns[1]
                    ? html`<span class="board-sub">${columns[1].format(row[columns[1].key])} ${columns[1].label}</span>`
                    : null
                }
              </li>`
            )}
          </ol>`
    }
    ${note ? html`<div class="board-note">${note}</div>` : null}
  </div>`;
}

export function table(rows, columns, { className = "" } = {}) {
  return html`<div class="table-wrap">
    <table class="data-table ${className}">
      <thead>
        <tr>
          ${columns.map((c) => html`<th class=${c.align === "left" ? "left" : ""}>${c.label}</th>`)}
        </tr>
      </thead>
      <tbody>
        ${rows.map(
          (row) => html`<tr>
            ${columns.map(
              (c) => html`<td class=${c.align === "left" ? "left" : ""}>
                ${c.format ? c.format(row[c.key], row) : row[c.key]}
              </td>`
            )}
          </tr>`
        )}
      </tbody>
    </table>
  </div>`;
}

export const num = (digits = 0) => (value) =>
  value == null || Number.isNaN(+value) ? "—" : (+value).toFixed(digits);

export const int = num(0);
