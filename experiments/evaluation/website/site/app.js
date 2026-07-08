const DATA_VERSION = "15";

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
let pipelineInstances = [];
let pipelineVariants = [];
let overview = {};

const state = {
  page: 1,
  pageSize: 15,
  selectedPipelineKey: null,
  showVariantComparison: false,
};

function byId(id) {
  return document.getElementById(id);
}

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
  return [...new Set(values.filter(value =>
    value !== null && value !== undefined && value !== ""
  ))];
}

function metricLabel(metric) {
  return METRIC_LABELS[metric] || metric;
}

function displayInstanceName(value) {
  if (value === null || value === undefined || value === "") return "—";

  return String(value)
    .split(/[\\/]/)
    .pop()
    .replace(/\.(json|pkl|pickle|csv|txt)$/i, "");
}

function selectedInstanceSet() {
  return byId("instanceSet").value;
}

function selectedMetric() {
  return byId("metric").value;
}

function mainRowsForSelectedSet() {
  const instanceSet = selectedInstanceSet();
  return results.filter(row => row.instance_set === instanceSet);
}

function overviewForSelectedSet() {
  const instanceSet = selectedInstanceSet();
  return overview?.by_instance_set?.find(row => row.instance_set === instanceSet) || null;
}

function availableMetrics(rows) {
  return METRICS.filter(metric =>
    rows.some(row =>
      isFiniteNumber(row[metric]) || isFiniteNumber(row[`${metric}_gap_pct`])
    )
  );
}

function instanceCount(rows) {
  const values = rows
    .map(row => Number(row.n_instances))
    .filter(Number.isFinite);

  if (values.length > 0) return Math.max(...values);

  const overviewRow = overviewForSelectedSet();
  return isFiniteNumber(overviewRow?.n_instances)
    ? Number(overviewRow.n_instances)
    : 0;
}

function rawResultCount(rows) {
  const values = rows
    .map(row => Number(row.n_result_rows))
    .filter(Number.isFinite);

  if (values.length > 0) {
    return values.reduce((sum, value) => sum + value, 0);
  }

  const overviewRow = overviewForSelectedSet();
  return isFiniteNumber(overviewRow?.raw_result_rows)
    ? Number(overviewRow.raw_result_rows)
    : 0;
}

function initControls() {
  const instanceSets = unique(results.map(row => row.instance_set)).sort();

  byId("instanceSet").innerHTML = instanceSets
    .map(value => `<option value="${esc(value)}">${esc(value)}</option>`)
    .join("");

  byId("instanceSet").addEventListener("change", () => {
    state.page = 1;
    state.selectedPipelineKey = null;
    state.showVariantComparison = false;
    updateMetricOptions();
    render();
  });

  byId("metric").addEventListener("change", () => {
    state.page = 1;
    state.showVariantComparison = false;
    render();
  });

  updateMetricOptions();
}

function updateMetricOptions() {
  const rows = mainRowsForSelectedSet();
  const metrics = availableMetrics(rows);
  const metricSelect = byId("metric");
  const previousMetric = metricSelect.value;

  metricSelect.innerHTML = metrics
    .map(metric => `<option value="${esc(metric)}">${esc(metricLabel(metric))}</option>`)
    .join("");

  if (metrics.includes(previousMetric)) {
    metricSelect.value = previousMetric;
  }
}

function renderSummaryCards() {
  const rows = mainRowsForSelectedSet();

  const cards = [
    ["Instances", instanceCount(rows)],
    ["Pipeline configurations", rows.length],
    ["Raw result rows", rawResultCount(rows)],
    ["Metrics", availableMetrics(rows).length],
  ];

  byId("summaryCards").innerHTML = cards.map(([label, value]) => `
    <div class="summary-card">
      <div class="summary-value">${Number(value).toLocaleString()}</div>
      <div class="summary-label">${esc(label)}</div>
    </div>
  `).join("");

  const scope = byId("reportScope");
  if (scope) scope.textContent = selectedInstanceSet();
}

function rankedMainRows() {
  const metric = selectedMetric();
  const gapMetric = `${metric}_gap_pct`;
  const bestMetric = `${metric}_best_count`;

  const rows = mainRowsForSelectedSet()
    .filter(row => isFiniteNumber(row[metric]) || isFiniteNumber(row[gapMetric]))
    .map(row => ({
      ...row,
      _value: isFiniteNumber(row[metric]) ? Number(row[metric]) : null,
      _gap: isFiniteNumber(row[gapMetric]) ? Number(row[gapMetric]) : Number.POSITIVE_INFINITY,
      _best: isFiniteNumber(row[bestMetric]) ? Number(row[bestMetric]) : 0,
    }));

  rows.sort((a, b) => {
    if (a._gap !== b._gap) return a._gap - b._gap;
    if (b._best !== a._best) return b._best - a._best;

    const aCpu = isFiniteNumber(a.total_cpu_time) ? Number(a.total_cpu_time) : Number.POSITIVE_INFINITY;
    const bCpu = isFiniteNumber(b.total_cpu_time) ? Number(b.total_cpu_time) : Number.POSITIVE_INFINITY;
    if (aCpu !== bCpu) return aCpu - bCpu;

    return String(a.pipeline_label || "").localeCompare(String(b.pipeline_label || ""));
  });

  let rank = 0;
  let lastGap = null;

  return rows.map(row => {
    if (lastGap === null || Math.abs(row._gap - lastGap) > 1e-9) {
      rank += 1;
      lastGap = row._gap;
    }

    return { ...row, rank };
  });
}

function renderMainTable() {
  const metric = selectedMetric();
  const rows = rankedMainRows();
  const pageSize = state.pageSize;
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));

  state.page = Math.max(1, Math.min(state.page, pageCount));

  const start = (state.page - 1) * pageSize;
  const end = start + pageSize;
  const pageRows = rows.slice(start, end);

  byId("performanceChart").innerHTML = `
    <div class="ranking-toolbar">
      <div class="ranking-count">
        Showing ${rows.length === 0 ? 0 : start + 1}–${Math.min(end, rows.length)}
        of ${rows.length} pipeline configurations
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

        <button id="rankingPrev" ${state.page <= 1 ? "disabled" : ""}>Previous</button>
        <span>Page ${state.page} / ${pageCount}</span>
        <button id="rankingNext" ${state.page >= pageCount ? "disabled" : ""}>Next</button>
      </div>
    </div>

    <div class="table-wrap">
      <table class="data-table main-table">
        <thead>
          <tr>
            <th class="num">Rank</th>
            <th>Item assignment</th>
            <th>Batching</th>
            <th>Routing</th>
            <th>Scheduling</th>
            <th class="num">Mean ${esc(metricLabel(metric))}</th>
            <th class="num">Deviation [%]</th>
            <th class="num">Best</th>
            <th class="num">Instances</th>
            <th class="num">CPU [s]</th>
          </tr>
        </thead>
        <tbody>
          ${pageRows.map((row, index) => `
            <tr
              class="clickable-row ${row.pipeline_key === state.selectedPipelineKey ? "is-selected" : ""} ${row._gap <= 1e-9 ? "is-best" : ""}"
              data-row-index="${index}"
              title="Click to show instance-level results"
            >
              <td class="num">${row.rank}</td>
              <td>${esc(row.item_assignment_algo || "—")}</td>
              <td>${esc(row.batching_algo || "—")}</td>
              <td>${esc(row.routing_algo || "—")}</td>
              <td>${esc(row.scheduling_algo || "—")}</td>
              <td class="num">${fmt(row._value)}</td>
              <td class="num">${fmt(row._gap)}</td>
              <td class="num">${Number(row._best || 0)} / ${Number(row.n_instances || 0)}</td>
              <td class="num">${Number(row.n_instances || 0)}</td>
              <td class="num">${fmt(row.total_cpu_time)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;

  byId("rankingPageSize").addEventListener("change", event => {
    state.pageSize = Number(event.target.value);
    state.page = 1;
    renderMainTable();
  });

  byId("rankingPrev").addEventListener("click", () => {
    state.page -= 1;
    renderMainTable();
  });

  byId("rankingNext").addEventListener("click", () => {
    state.page += 1;
    renderMainTable();
  });

  document.querySelectorAll(".clickable-row").forEach(rowElement => {
    rowElement.addEventListener("click", () => {
      const row = pageRows[Number(rowElement.dataset.rowIndex)];
      state.selectedPipelineKey = row.pipeline_key;
      state.showVariantComparison = false;
      renderMainTable();
      renderDetailPanel();
    });
  });
}

function selectedMainRow() {
  if (!state.selectedPipelineKey) return null;

  return mainRowsForSelectedSet()
    .find(row => row.pipeline_key === state.selectedPipelineKey) || null;
}

function selectedInstanceRows() {
  const metric = selectedMetric();
  const gapMetric = `${metric}_gap_pct`;

  return pipelineInstances
    .filter(row =>
      row.instance_set === selectedInstanceSet() &&
      row.pipeline_key === state.selectedPipelineKey
    )
    .map(row => ({
      ...row,
      _value: isFiniteNumber(row[metric]) ? Number(row[metric]) : null,
      _gap: isFiniteNumber(row[gapMetric]) ? Number(row[gapMetric]) : Number.POSITIVE_INFINITY,
      _isBest: Boolean(row[`${metric}_is_best`]),
    }))
    .sort((a, b) => {
      if (a._gap !== b._gap) return a._gap - b._gap;
      return String(a.instance_name || "").localeCompare(String(b.instance_name || ""));
    });
}

function selectedVariantRows() {
  const metric = selectedMetric();
  const gapMetric = `${metric}_gap_pct`;
  const bestMetric = `${metric}_best_count`;

  return pipelineVariants
    .filter(row =>
      row.instance_set === selectedInstanceSet() &&
      row.pipeline_key === state.selectedPipelineKey
    )
    .map(row => ({
      ...row,
      _value: isFiniteNumber(row[metric]) ? Number(row[metric]) : null,
      _gap: isFiniteNumber(row[gapMetric]) ? Number(row[gapMetric]) : Number.POSITIVE_INFINITY,
      _best: isFiniteNumber(row[bestMetric]) ? Number(row[bestMetric]) : 0,
    }))
    .sort((a, b) => {
      if (a._gap !== b._gap) return a._gap - b._gap;
      if (b._best !== a._best) return b._best - a._best;
      return String(a.pipeline_version_label || "").localeCompare(String(b.pipeline_version_label || ""));
    });
}

function renderDetailPanel() {
  const detailPanel = byId("detailPanel");
  const detailContent = byId("detailContent");

  if (!state.selectedPipelineKey) {
    detailPanel.hidden = true;
    detailContent.innerHTML = "";
    return;
  }

  const mainRow = selectedMainRow();
  if (!mainRow) {
    detailPanel.hidden = true;
    detailContent.innerHTML = "";
    return;
  }

  const metric = selectedMetric();
  const label = metricLabel(metric);

  const value = isFiniteNumber(mainRow[metric]) ? Number(mainRow[metric]) : null;
  const gap = isFiniteNumber(mainRow[`${metric}_gap_pct`]) ? Number(mainRow[`${metric}_gap_pct`]) : null;
  const bestCount = isFiniteNumber(mainRow[`${metric}_best_count`]) ? Number(mainRow[`${metric}_best_count`]) : 0;

  const instanceRows = selectedInstanceRows();
  const variantRows = selectedVariantRows();

  detailPanel.hidden = false;

  detailContent.innerHTML = `
    <div class="detail-header">
      <div>
        <h2>Pipeline-level results</h2>
        <p class="hint">
          ${esc(mainRow.pipeline_label || "unknown pipeline")} over all instances in ${esc(selectedInstanceSet())}.
        </p>
      </div>

      <button id="closeDetail">Close details</button>
    </div>

    <div class="detail-summary">
      <div class="summary-card">
        <div class="summary-value">${fmt(value)}</div>
        <div class="summary-label">Mean ${esc(label)}</div>
      </div>

      <div class="summary-card">
        <div class="summary-value">${fmt(gap)}</div>
        <div class="summary-label">Mean deviation [%]</div>
      </div>

      <div class="summary-card">
        <div class="summary-value">${bestCount} / ${Number(mainRow.n_instances || 0)}</div>
        <div class="summary-label">Best instances</div>
      </div>

      <div class="summary-card">
        <div class="summary-value">${fmt(mainRow.total_cpu_time)}</div>
        <div class="summary-label">Mean CPU [s]</div>
      </div>
    </div>

    <h3>Instance-level results</h3>
    <p class="hint">
      Each row shows how this pipeline configuration performed on one instance for the selected metric.
    </p>

    <div class="table-wrap">
      <table class="data-table instance-table">
        <thead>
          <tr>
            <th>Instance</th>
            <th class="num">${esc(label)}</th>
            <th class="num">Deviation [%]</th>
            <th class="num">Best</th>
            <th class="num">CPU [s]</th>
          </tr>
        </thead>
        <tbody>
          ${instanceRows.map(row => `
            <tr class="${row._isBest ? "is-best" : ""}">
              <td>
                <span class="instance-name" title="${esc(row.instance_name || "")}">
                  ${esc(displayInstanceName(row.instance_name))}
                </span>
              </td>
              <td class="num">${fmt(row._value)}</td>
              <td class="num">${fmt(row._gap)}</td>
              <td class="num">${row._isBest ? "yes" : "no"}</td>
              <td class="num">${fmt(row.total_cpu_time)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>

    <div class="detail-actions">
      <button id="toggleVariants">
        ${state.showVariantComparison ? "Hide configuration variants" : "Show configuration variants"}
      </button>
    </div>

    <div id="variantComparison" ${state.showVariantComparison ? "" : "hidden"}>
      <h3>Configuration variant comparison</h3>
      <p class="hint">
        Each row is one concrete variant of the selected pipeline configuration aggregated over the selected instance set.
      </p>

      <div class="table-wrap">
        <table class="data-table variant-table">
          <thead>
            <tr>
              <th>Variant</th>
              <th class="num">Mean ${esc(label)}</th>
              <th class="num">Deviation [%]</th>
              <th class="num">Best</th>
              <th class="num">Instances</th>
              <th class="num">CPU [s]</th>
            </tr>
          </thead>
          <tbody>
            ${variantRows.map(row => `
              <tr class="${row._gap <= 1e-9 ? "is-best" : ""}">
                <td>
                  <span class="variant-label" title="${esc(row.pipeline_version_key || "")}">
                    ${esc(row.pipeline_version_label || "unknown variant")}
                  </span>
                </td>
                <td class="num">${fmt(row._value)}</td>
                <td class="num">${fmt(row._gap)}</td>
                <td class="num">${Number(row._best || 0)} / ${Number(row.n_instances || 0)}</td>
                <td class="num">${Number(row.n_instances || 0)}</td>
                <td class="num">${fmt(row.total_cpu_time)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;

  byId("closeDetail").addEventListener("click", () => {
    state.selectedPipelineKey = null;
    state.showVariantComparison = false;
    render();
  });

  byId("toggleVariants").addEventListener("click", () => {
    state.showVariantComparison = !state.showVariantComparison;
    renderDetailPanel();
  });
}

function render() {
  renderSummaryCards();
  renderMainTable();
  renderDetailPanel();
}

async function loadJson(path) {
  const response = await fetch(`${path}?v=${DATA_VERSION}`);

  if (!response.ok) {
    throw new Error(`Could not load ${path}: ${response.status}`);
  }

  return response.json();
}

async function main() {
  [
    results,
    pipelineInstances,
    pipelineVariants,
    overview,
  ] = await Promise.all([
    loadJson("data/results.json"),
    loadJson("data/pipeline_instances.json"),
    loadJson("data/pipeline_versions.json"),
    loadJson("data/overview.json"),
  ]);

  initControls();
  render();
}

main().catch(error => {
  console.error(error);
  document.body.innerHTML = `<pre>${esc(error.stack || error)}</pre>`;
});