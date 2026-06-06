const state = {
  runs: [],
  selectedRunId: null,
  pollTimer: null,
};

const form = document.querySelector("#run-form");
const cancelButton = document.querySelector("#cancel-button");
const refreshButton = document.querySelector("#refresh-button");
const traceRefresh = document.querySelector("#trace-refresh");
const traceFilter = document.querySelector("#trace-filter");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.agents = Number(payload.agents);
  payload.days = Number(payload.days);
  payload.sessions = Number(payload.sessions);
  payload.seed = payload.seed === "" ? null : Number(payload.seed);
  payload.fee_rate = Number(payload.fee_rate);
  payload.slippage_rate = Number(payload.slippage_rate);
  payload.daily_limit_pct = Number(payload.daily_limit_pct);
  payload.max_fill_per_level = Number(payload.max_fill_per_level);
  payload.order_ttl_sessions = Number(payload.order_ttl_sessions);

  const run = await requestJson("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.selectedRunId = run.id;
  await refreshRuns();
  startPolling();
});

cancelButton.addEventListener("click", async () => {
  if (!state.selectedRunId) return;
  await requestJson(`/api/runs/${state.selectedRunId}`, { method: "DELETE" });
  await refreshRuns();
});

refreshButton.addEventListener("click", refreshRuns);
traceRefresh.addEventListener("click", () => loadTrace(state.selectedRunId));

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`#${tab.dataset.tab}-tab`).classList.add("active");
    if (tab.dataset.tab === "trace") {
      loadTrace(state.selectedRunId);
    }
  });
});

async function init() {
  await loadDefaults();
  await refreshRuns();
  startPolling();
}

async function loadDefaults() {
  const defaults = await requestJson("/api/defaults");
  for (const [key, value] of Object.entries(defaults)) {
    const input = form.elements[key];
    if (input) input.value = value;
  }
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    const selected = currentRun();
    if (!selected || ["running", "queued"].includes(selected.status)) {
      await refreshRuns({ quiet: true });
    }
  }, 1500);
}

async function refreshRuns() {
  const response = await requestJson("/api/runs");
  state.runs = response.runs || [];
  if (!state.selectedRunId && state.runs.length) {
    state.selectedRunId = state.runs[0].id;
  }
  renderRuns();
  renderSelectedRun();
}

function renderRuns() {
  const list = document.querySelector("#runs-list");
  document.querySelector("#run-count").textContent = String(state.runs.length);
  if (!state.runs.length) {
    list.innerHTML = `<div class="empty">No runs</div>`;
    return;
  }

  list.innerHTML = state.runs.map((run) => `
    <button class="run-item ${run.id === state.selectedRunId ? "active" : ""}" data-run-id="${run.id}">
      <span class="run-topline">
        <span class="run-id">${escapeHtml(run.id)}</span>
        <span class="badge ${escapeHtml(run.status)}">${escapeHtml(run.status)}</span>
      </span>
      <span>${formatDate(run.created_at)} · ${formatDuration(run.duration_seconds)}</span>
    </button>
  `).join("");

  list.querySelectorAll(".run-item").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedRunId = button.dataset.runId;
      renderRuns();
      renderSelectedRun();
    });
  });
}

function renderSelectedRun() {
  const run = currentRun();
  const isRunning = run && ["running", "queued"].includes(run.status);
  cancelButton.disabled = !isRunning;

  document.querySelector("#status-value").textContent = run ? run.status : "Idle";
  document.querySelector("#trades-value").textContent = stat(run, "trades");
  document.querySelector("#trace-value").textContent = stat(run, "trace_events");
  document.querySelector("#duration-value").textContent = run ? formatDuration(run.duration_seconds) : "-";
  document.querySelector("#output-dir").textContent = run ? run.output_dir : "-";
  document.querySelector("#agent-days").textContent = stat(run, "agent_days");
  document.querySelector("#agent-sessions").textContent = stat(run, "agent_sessions");
  document.querySelector("#command-view").textContent = run ? run.command.join(" ") : "";
  document.querySelector("#stderr-view").textContent = run ? run.stderr_tail || "" : "";
  document.querySelector("#stdout-view").textContent = run ? run.stdout_tail || "" : "";

  const lastPrices = run?.summary?.last_prices;
  document.querySelector("#last-prices").textContent = lastPrices ? JSON.stringify(lastPrices) : "-";
  renderFiles(run);
  if (document.querySelector("#trace-tab").classList.contains("active")) {
    loadTrace(run?.id);
  }
}

function renderFiles(run) {
  const filesList = document.querySelector("#files-list");
  if (!run || !run.files?.length) {
    filesList.innerHTML = `<div class="empty">No files</div>`;
    return;
  }

  filesList.innerHTML = run.files.map((file) => `
    <div class="file-item">
      <span>
        <strong>${escapeHtml(file.name)}</strong>
        <small>${formatBytes(file.size)}</small>
      </span>
      <a href="/api/runs/${run.id}/file?name=${encodeURIComponent(file.name)}">Download</a>
    </div>
  `).join("");
}

async function loadTrace(runId) {
  const traceList = document.querySelector("#trace-list");
  if (!runId) {
    traceList.innerHTML = `<div class="empty">No run selected</div>`;
    return;
  }
  const filter = traceFilter.value;
  const url = `/api/runs/${runId}/trace?limit=80${filter ? `&event_type=${encodeURIComponent(filter)}` : ""}`;
  const response = await requestJson(url);
  const events = response.events || [];
  if (!events.length) {
    traceList.innerHTML = `<div class="empty">No trace events</div>`;
    return;
  }
  traceList.innerHTML = events.map((event) => `
    <article class="trace-event">
      <header>
        <strong>${escapeHtml(event.event_type)}</strong>
        <span>#${event.sequence || ""}</span>
      </header>
      <pre>${escapeHtml(JSON.stringify(event, null, 2))}</pre>
    </article>
  `).join("");
}

function currentRun() {
  return state.runs.find((run) => run.id === state.selectedRunId) || null;
}

function stat(run, key) {
  const value = run?.summary?.[key];
  return value === null || value === undefined ? "-" : String(value);
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function formatDate(timestamp) {
  if (!timestamp) return "-";
  return new Date(timestamp * 1000).toLocaleTimeString();
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  return `${seconds}s`;
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

init().catch((error) => {
  document.querySelector("#status-value").textContent = error.message;
});
