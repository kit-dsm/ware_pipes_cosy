const METRICS = [
  "total_distance",
  "total_cpu_time",
  "makespan",
  "on_time_rate",
  "max_tardiness",
  "avg_tardiness",
  "avg_lateness",
  "max_lateness",
];

const METRIC_LABELS = {
  total_distance: "Total distance",
  total_cpu_time: "CPU time",
  makespan: "Makespan",
  on_time_rate: "On-time rate",
  max_tardiness: "Max tardiness",
  avg_tardiness: "Avg. tardiness",
  avg_lateness: "Avg. lateness",
  max_lateness: "Max lateness",
};

let results = [];
let overview = {};

let rankingState = {
  page: 1,
  pageSize: 15,
};

function isFiniteNumber(value) {
  return Number.isFinite(Number(value));
}

function fmt(value, digits = 3) {
  if (!isFiniteNumber(value)) return "—";

  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

function esc(value) {
  if (value === null || value === undefined) return "";

  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function unique(values) {
  return [...new Set(values.filter(v => v !== null && v !== undefined && v !== ""))];
}

function selectedInstanceSet() {
  return document.getElementById("instanceSet").value;
}

function selectedMetric() {
  return document.getElementById("metric").value;
}

function rowsForSelectedInstanceSet() {
  const instanceSet = selectedInstanceSet();
  return results.filter(r => r.instance_set === instanceSet);
}

function availableMetrics(rows) {
  return METRICS.filter(metric =>
    rows.some(row => isFiniteNumber(row[metric]) || isFiniteNumber(row[`${metric}_gap_pct`]))
  );
}

function instanceCountForSelectedSet(rows) {
  const fromRows = rows
    .map(r => Number(r.n_instances))
    .filter(Number.isFinite);

  if (fromRows.length > 0) {
    return Math.max(...fromRows);
  }

  const instanceSet = selectedInstanceSet();

  const overviewRow = overview?.by_instance_set?.find(r => r.instance_set === instanceSet);
  if (overviewRow && isFiniteNumber(overviewRow.n_instances)) {
    return Number(overviewRow.n_instances);
  }

  return 0;
}

function rawResultRowsForSelectedSet(rows) {
  const fromRows = rows
    .map(r => Number(r.n_result_rows))
    .filter(Number.isFinite);

  if (fromRows.length > 0) {
    return fromRows.reduce((sum, value) => sum + value, 0);
  }

  const instanceSet = selectedInstanceSet();

  const overviewRow = overview?.by_instance_set?.find(r => r.instance_set === instanceSet);
  if (overviewRow && isFiniteNumber(overviewRow.raw_result_rows)) {
    return Number(overviewRow.raw_result_rows);
  }

  return 0;
}

function initControls() {
  const instanceSets = unique(results.map(r => r.instance_set)).sort();

  const instanceSetSelect = document.getElementById("instanceSet");
  instanceSetSelect.innerHTML = instanceSets
    .map(instanceSet => `<option value="${esc(instanceSet)}">${esc(instanceSet)}</option>`)
    .join("");

  instanceSetSelect.addEventListener("change", () => {
    rankingState.page = 1;
    updateMetricOptions();
    render();
  });

  const metricSelect = document.getElementById("metric");
  metricSelect.addEventListener("change", () => {
    rankingState.page = 1;
    render();
  });

  updateMetricOptions();
}

function updateMetricOptions() {
  const rows = rowsForSelectedInstanceSet();
  const metrics = availableMetrics(rows);

  const metricSelect = document.getElementById("metric");
  const previousMetric = metricSelect.value;

  metricSelect.innerHTML = metrics
    .map(metric => `<option value="${esc(metric)}">${esc(METRIC_LABELS[metric] || metric)}</option>`)
    .join("");

  if (metrics.includes(previousMetric)) {
    metricSelect.value = previousMetric;
  }
}

function renderSummaryCards() {
  const rows = rowsForSelectedInstanceSet();

  const cards = [
    ["Instances", instanceCountForSelectedSet(rows)],
    ["Configurations", rows.length],
    ["Raw result rows", rawResultRowsForSelectedSet(rows)],
    ["Metrics", availableMetrics(rows).length],
  ];

  document.getElementById("summaryCards").innerHTML = cards.map(([label, value]) => `
    <div class="summary-card">
      <div class="summary-value">${Number(value).toLocaleString()}</div>
      <div class="summary-label">${esc(label)}</div>
    </div>
  `).join("");

  const scope = document.getElementById("reportScope");
  if (scope) {
    scope.textContent = selectedInstanceSet();
  }
}

function rankedRows() {
  const metric = selectedMetric();
  const gapMetric = `${metric}_gap_pct`;
  const bestMetric = `${metric}_best_count`;

  const rows = rowsForSelectedInstanceSet()
    .filter(row => isFiniteNumber(row[metric]) || isFiniteNumber(row[gapMetric]))
    .map(row => {
      const value = isFiniteNumber(row[metric]) ? Number(row[metric]) : null;
      const gap = isFiniteNumber(row[gapMetric])
        ? Number(row[gapMetric])
        : Number.POSITIVE_INFINITY;

      return {
        ...row,
        _value: value,
        _gap: gap,
        _best: isFiniteNumber(row[bestMetric]) ? Number(row[bestMetric]) : 0,
      };
    });

  rows.sort((a, b) => {
    if (a._gap !== b._gap) return a._gap - b._gap;
    if (b._best !== a._best) return b._best - a._best;

    const aCpu = isFiniteNumber(a.total_cpu_time) ? Number(a.total_cpu_time) : Number.POSITIVE_INFINITY;
    const bCpu = isFiniteNumber(b.total_cpu_time) ? Number(b.total_cpu_time) : Number.POSITIVE_INFINITY;
    if (aCpu !== bCpu) return aCpu - bCpu;

    return String(a.strategy_versioned || a.strategy || "").localeCompare(
      String(b.strategy_versioned || b.strategy || "")
    );
  });

  let rank = 0;
  let lastGap = null;

  return rows.map(row => {
    if (lastGap === null || Math.abs(row._gap - lastGap) > 1e-9) {
      rank += 1;
      lastGap = row._gap;
    }

    return {
      ...row,
      rank,
    };
  });
}

function renderPerformanceChart() {
  const metric = selectedMetric();
  const rows = rankedRows();
  const nInstances = instanceCountForSelectedSet(rows);

  const pageSize = rankingState.pageSize;
  const nPages = Math.max(1, Math.ceil(rows.length / pageSize));

  rankingState.page = Math.max(1, Math.min(rankingState.page, nPages));

  const start = (rankingState.page - 1) * pageSize;
  const end = start + pageSize;
  const pageRows = rows.slice(start, end);

  const firstShown = rows.length === 0 ? 0 : start + 1;
  const lastShown = Math.min(end, rows.length);

  const html = `
    <div class="ranking-toolbar">
      <div class="ranking-count">
        Showing ${firstShown}–${lastShown} of ${rows.length} configurations
      </div>

      <div class="ranking-controls">
        <label>
          Rows
          <select id="rankingPageSize">
            ${[10, 15, 25, 50, 100].map(size => `
              <option value="${size}" ${size === pageSize ? "selected" : ""}>${size}</option>
            `).join("")}
          </select>
        </label>

        <button id="rankingPrev" ${rankingState.page <= 1 ? "disabled" : ""}>Previous</button>
        <span>Page ${rankingState.page} / ${nPages}</span>
        <button id="rankingNext" ${rankingState.page >= nPages ? "disabled" : ""}>Next</button>
      </div>
    </div>

    <div class="ranking-table-scroll">
      <table class="ranking-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Item assignment</th>
            <th>Batching</th>
            <th>Routing</th>
            <th>Scheduling</th>
            <th>Mean ${esc(METRIC_LABELS[metric] || metric)}</th>
            <th>Deviation [%]</th>
            <th>Best</th>
            <th>Instances</th>
            <th>CPU [s]</th>
          </tr>
        </thead>

        <tbody>
          ${pageRows.map(row => `
            <tr class="${row._gap <= 1e-9 ? "rank-best" : ""}" title="${esc(row.strategy_versioned || row.strategy || "")}">
              <td>${row.rank}</td>
              <td>${esc(row.item_assignment_algo || "—")}</td>
              <td>${esc(row.batching_algo || "—")}</td>
              <td>${esc(row.routing_algo || "—")}</td>
              <td>${esc(row.scheduling_algo || "—")}</td>
              <td>${fmt(row._value)}</td>
              <td>${fmt(row._gap)}</td>
              <td>${Number(row._best || 0)} / ${nInstances}</td>
              <td>${nInstances}</td>
              <td>${fmt(row.total_cpu_time)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;

  document.getElementById("performanceChart").innerHTML = html;

  document.getElementById("rankingPageSize").addEventListener("change", event => {
    rankingState.pageSize = Number(event.target.value);
    rankingState.page = 1;
    renderPerformanceChart();
  });

  document.getElementById("rankingPrev").addEventListener("click", () => {
    rankingState.page -= 1;
    renderPerformanceChart();
  });

  document.getElementById("rankingNext").addEventListener("click", () => {
    rankingState.page += 1;
    renderPerformanceChart();
  });
}

function render() {
  renderSummaryCards();
  renderPerformanceChart();
}

async function main() {
  const [resultsResponse, overviewResponse] = await Promise.all([
    fetch("data/results.json?v=12"),
    fetch("data/overview.json?v=12"),
  ]);

  if (!resultsResponse.ok) {
    throw new Error(`Could not load results.json: ${resultsResponse.status}`);
  }

  if (!overviewResponse.ok) {
    throw new Error(`Could not load overview.json: ${overviewResponse.status}`);
  }

  results = await resultsResponse.json();
  overview = await overviewResponse.json();

  initControls();
  render();
}

main().catch(error => {
  console.error(error);
  document.body.innerHTML = `<pre>${esc(error.stack || error)}</pre>`;
});