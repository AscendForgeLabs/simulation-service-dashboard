const state = {
  jobs: [],
  selectedJobId: new URLSearchParams(window.location.search).get("job"),
  detail: null,
  audit: [],
  selectedAudit: null,
  pollTimer: null,
  activeView: "simulation",
  ansysJobs: [],
  selectedAnsysJobId: null,
  ansysLogSource: "job.log",
};

const elements = {
  connection: document.querySelector("#connection"),
  refreshJobs: document.querySelector("#refresh-jobs"),
  uploadForm: document.querySelector("#upload-form"),
  jobList: document.querySelector("#job-list"),
  pollState: document.querySelector("#poll-state"),
  statusGrid: document.querySelector("#status-grid"),
  jobError: document.querySelector("#job-error"),
  processSummary: document.querySelector("#process-summary"),
  processChart: document.querySelector("#process-chart"),
  reportState: document.querySelector("#report-state"),
  densityGrid: document.querySelector("#density-grid"),
  acceptanceList: document.querySelector("#acceptance-list"),
  artifactList: document.querySelector("#artifact-list"),
  artifactCount: document.querySelector("#artifact-count"),
  auditList: document.querySelector("#audit-list"),
  auditDetail: document.querySelector("#audit-detail"),
  auditCount: document.querySelector("#audit-count"),
  eventList: document.querySelector("#event-list"),
  eventCount: document.querySelector("#event-count"),
  simulationTab: document.querySelector("#simulation-tab"),
  ansysTab: document.querySelector("#ansys-tab"),
  simulationView: document.querySelector("#simulation-view"),
  ansysView: document.querySelector("#ansys-view"),
  refreshAnsys: document.querySelector("#refresh-ansys"),
  ansysJobList: document.querySelector("#ansys-job-list"),
  ansysHealthState: document.querySelector("#ansys-health-state"),
  ansysHealthGrid: document.querySelector("#ansys-health-grid"),
  ansysJobState: document.querySelector("#ansys-job-state"),
  ansysJobGrid: document.querySelector("#ansys-job-grid"),
  ansysJobError: document.querySelector("#ansys-job-error"),
  ansysJobLog: document.querySelector("#ansys-job-log"),
  ansysServiceLog: document.querySelector("#ansys-service-log"),
  ansysServiceLogState: document.querySelector("#ansys-service-log-state"),
  ansysArtifactList: document.querySelector("#ansys-artifact-list"),
  ansysArtifactCount: document.querySelector("#ansys-artifact-count"),
  jobLogTab: document.querySelector("#job-log-tab"),
  solverLogTab: document.querySelector("#solver-log-tab"),
};

async function request(path, options = {}) {
  const response = await fetch(path, { headers: { Accept: "application/json" }, ...options });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || JSON.stringify(body);
    } catch (_) {
      // Keep the HTTP status as the message.
    }
    throw new Error(message);
  }
  return response.json();
}

async function requestText(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.text();
}

async function loadJobs() {
  try {
    state.jobs = await request("/api/simulations");
    setConnection(true, `${state.jobs.length} 个任务`);
  } catch (error) {
    state.jobs = [];
    setConnection(false, "连接失败");
  }
  renderJobs();
  if (!state.selectedJobId && state.jobs.length > 0) {
    await selectJob(state.jobs[0].job_id);
  }
}

async function selectJob(jobId, pushUrl = true) {
  state.selectedJobId = jobId;
  state.audit = [];
  state.selectedAudit = null;
  if (pushUrl) {
    const url = new URL(window.location.href);
    url.searchParams.set("job", jobId);
    window.history.replaceState(null, "", url);
  }
  renderJobs();
  await refreshDetail();
}

async function refreshDetail() {
  const jobId = state.selectedJobId;
  if (!jobId) return;
  try {
    state.detail = await request(`/api/simulations/${jobId}`);
    renderDetail();
    await loadAudit(jobId);
  } catch (error) {
    state.detail = null;
    renderDetail();
    showGlobalError(error.message);
  }
}

async function loadAudit(jobId) {
  try {
    state.audit = await request(`/api/simulations/${jobId}/http-audit`);
  } catch (_) {
    state.audit = [];
  }
  renderAudit();
}

async function selectAudit(sequence) {
  if (!state.selectedJobId) return;
  state.selectedAudit = sequence;
  try {
    const detail = await request(`/api/simulations/${state.selectedJobId}/http-audit/${sequence}`);
    renderAuditDetail(detail);
  } catch (error) {
    elements.auditDetail.textContent = error.message;
  }
}

async function loadAnsys() {
  try {
    const [health, jobs, serviceLog] = await Promise.all([
      request("/api/ansys/health"),
      request("/api/ansys/jobs"),
      requestText("/api/ansys/service-log"),
    ]);
    renderAnsysHealth(health);
    state.ansysJobs = jobs;
    elements.ansysServiceLog.textContent = serviceLog.split("\n").slice(-200).join("\n");
    setConnection(true, "下游可用");
  } catch (error) {
    elements.ansysHealthState.textContent = "连接失败";
    state.ansysJobs = [];
    elements.ansysServiceLog.textContent = error.message;
    setConnection(false, "下游不可用");
  }
  renderAnsysJobs();
  if (!state.selectedAnsysJobId && state.ansysJobs.length > 0) {
    await selectAnsysJob(state.ansysJobs[0].id);
  }
}

async function selectAnsysJob(jobId) {
  state.selectedAnsysJobId = jobId;
  renderAnsysJobs();
  await loadAnsysJobDetail();
}

async function loadAnsysJobDetail() {
  const jobId = state.selectedAnsysJobId;
  if (!jobId) return;
  const job = state.ansysJobs.find((item) => item.id === jobId);
  renderAnsysJob(job);
  try {
    const [jobLog, artifacts] = await Promise.all([
      requestText(`/api/ansys/jobs/${jobId}/log?source=${state.ansysLogSource}`),
      request(`/api/ansys/jobs/${jobId}/artifacts`),
    ]);
    elements.ansysJobLog.textContent = jobLog;
    renderAnsysArtifacts(jobId, artifacts);
  } catch (error) {
    elements.ansysJobLog.textContent = error.message;
    renderAnsysArtifacts(jobId, []);
  }
}

function switchView(view) {
  state.activeView = view;
  const simulationActive = view === "simulation";
  elements.simulationTab.classList.toggle("active", simulationActive);
  elements.ansysTab.classList.toggle("active", !simulationActive);
  elements.simulationView.classList.toggle("hidden", !simulationActive);
  elements.ansysView.classList.toggle("hidden", simulationActive);
  setConnection(simulationActive, "上游未连接", false);
}

async function submitSimulation(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector("button[type=submit]");
  submitButton.disabled = true;
  try {
    const created = await request("/api/simulations", {
      method: "POST",
      body: new FormData(form),
    });
    await loadJobs();
    await selectJob(created.job_id);
    form.reset();
  } catch (error) {
    showGlobalError(error.message);
  } finally {
    submitButton.disabled = false;
  }
}

function setConnection(online, text) {
  elements.connection.textContent = text;
  elements.connection.classList.toggle("online", online);
  elements.connection.classList.toggle("offline", !online);
}

function renderJobs() {
  if (state.jobs.length === 0) {
    elements.jobList.innerHTML = '<div class="empty">暂无任务</div>';
    return;
  }
  elements.jobList.replaceChildren(
    ...state.jobs.map((job) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `job-item${job.job_id === state.selectedJobId ? " selected" : ""}`;
      const title = document.createElement("div");
      title.className = "job-title";
      const status = document.createElement("strong");
      status.textContent = statusText(job.status);
      const time = document.createElement("span");
      time.className = "job-created";
      time.textContent = formatTime(job.created_at);
      title.append(status, time);
      const id = document.createElement("div");
      id.className = "job-id";
      id.textContent = job.job_id;
      button.append(title, id);
      button.addEventListener("click", () => selectJob(job.job_id));
      return button;
    })
  );
}

function renderAnsysJobs() {
  if (state.ansysJobs.length === 0) {
    elements.ansysJobList.innerHTML = '<div class="empty">暂无下游作业</div>';
    return;
  }
  elements.ansysJobList.replaceChildren(
    ...state.ansysJobs.map((job) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `job-item${job.id === state.selectedAnsysJobId ? " selected" : ""}`;
      const title = document.createElement("div");
      title.className = "job-title";
      const status = document.createElement("strong");
      status.textContent = job.status;
      const time = document.createElement("span");
      time.className = "job-created";
      time.textContent = formatTime(job.created_at);
      title.append(status, time);
      const id = document.createElement("div");
      id.className = "job-id";
      id.textContent = job.id;
      button.append(title, id);
      button.addEventListener("click", () => selectAnsysJob(job.id));
      return button;
    })
  );
}

function renderDetail() {
  const detail = state.detail;
  if (!detail) {
    elements.pollState.textContent = "未选择任务";
    elements.statusGrid.innerHTML = "";
    elements.jobError.classList.add("hidden");
    return;
  }
  elements.pollState.textContent = detail.status;
  const fields = [
    ["任务状态", detail.status],
    ["系统状态", detail.system_status],
    ["求解器", detail.solver_status || "-"],
    ["仿真判定", detail.simulation_status || "-"],
    ["远程 Ansys Job", detail.remote_job_id || "-"],
  ];
  elements.statusGrid.replaceChildren(
    ...fields.map(([label, value]) => {
      const card = document.createElement("div");
      card.className = "status-card";
      const labelElement = document.createElement("div");
      labelElement.className = "status-label";
      labelElement.textContent = label;
      const valueElement = document.createElement("div");
      valueElement.className = `status-value ${String(value).toLowerCase()}`;
      valueElement.textContent = value;
      card.append(labelElement, valueElement);
      return card;
    })
  );

  if (detail.error) {
    elements.jobError.textContent = `${detail.error.error_code}: ${detail.error.message}`;
    elements.jobError.classList.remove("hidden");
  } else {
    elements.jobError.classList.add("hidden");
  }

  renderProcess(detail.result?.process);
  renderReport(detail);
  renderArtifacts(detail.result?.artifacts || {});
  renderEvents(detail.events || []);
}

function renderAnsysHealth(health) {
  elements.ansysHealthState.textContent = health.status || "-";
  const fields = [
    ["服务状态", health.status],
    ["MAPDL", health.mapdl_found ? "可用" : "不可用"],
    ["License", health.license_env_set ? "可用" : "不可用"],
    ["Passthrough", health.passthrough_enabled ? "开启" : "关闭"],
    ["运行队列", health.queue_running],
    ["等待队列", health.queue_pending],
    ["版本", health.version],
  ];
  renderStatusCards(elements.ansysHealthGrid, fields);
}

function renderAnsysJob(job) {
  if (!job) {
    elements.ansysJobState.textContent = "未选择作业";
    elements.ansysJobGrid.innerHTML = "";
    return;
  }
  elements.ansysJobState.textContent = job.status;
  const fields = [
    ["作业 ID", job.id],
    ["方法", job.method],
    ["状态", job.status],
    ["保真度", job.fidelity || "-"],
    ["创建时间", formatTime(job.created_at)],
    ["开始时间", formatTime(job.started_at)],
    ["结束时间", formatTime(job.finished_at)],
  ];
  renderStatusCards(elements.ansysJobGrid, fields);
  if (job.error) {
    elements.ansysJobError.textContent = `${job.error.code}: ${job.error.message}`;
    elements.ansysJobError.classList.remove("hidden");
  } else {
    elements.ansysJobError.classList.add("hidden");
  }
}

function renderStatusCards(container, fields) {
  container.replaceChildren(
    ...fields.map(([label, value]) => {
      const card = document.createElement("div");
      card.className = "status-card";
      const labelElement = document.createElement("div");
      labelElement.className = "status-label";
      labelElement.textContent = label;
      const valueElement = document.createElement("div");
      valueElement.className = `status-value ${String(value).toLowerCase()}`;
      valueElement.textContent = value ?? "-";
      card.append(labelElement, valueElement);
      return card;
    })
  );
}

function renderProcess(process) {
  const summary = process?.summary;
  if (!summary) {
    elements.processSummary.innerHTML = "";
    elements.processChart.innerHTML = "";
    return;
  }
  const values = [
    ["峰值温度", `${formatNumber(summary.peak_temperature_celsius)} C`],
    ["峰值压力", `${formatNumber(summary.peak_pressure_mpa)} MPa`],
    ["总时长", `${formatNumber(summary.duration_hours)} h`],
  ];
  elements.processSummary.replaceChildren(
    ...values.map(([label, value]) => {
      const block = document.createElement("div");
      const labelElement = document.createElement("span");
      labelElement.textContent = label;
      const valueElement = document.createElement("span");
      valueElement.textContent = value;
      block.append(labelElement, valueElement);
      return block;
    })
  );
  renderProcessChart(process.points || []);
}

function renderProcessChart(points) {
  elements.processChart.replaceChildren();
  if (points.length === 0) return;
  const width = Math.max(elements.processChart.clientWidth, 300);
  const height = elements.processChart.clientHeight || 230;
  const margin = { top: 16, right: 12, bottom: 26, left: 44 };
  const maxTime = Math.max(...points.map((point) => point.time_hours), 1);
  const maxTemp = Math.max(...points.map((point) => point.temperature_celsius), 1);
  const maxPressure = Math.max(...points.map((point) => point.pressure_mpa), 1);
  const x = (time) => margin.left + (time / maxTime) * (width - margin.left - margin.right);
  const yTemp = (temp) => height - margin.bottom - (temp / maxTemp) * (height - margin.top - margin.bottom);
  const yPressure = (pressure) => height - margin.bottom - (pressure / maxPressure) * (height - margin.top - margin.bottom);
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");

  [0, 0.25, 0.5, 0.75, 1].forEach((ratio) => {
    const y = margin.top + ratio * (height - margin.top - margin.bottom);
    const line = document.createElementNS(namespace, "line");
    line.setAttribute("x1", margin.left);
    line.setAttribute("x2", width - margin.right);
    line.setAttribute("y1", y);
    line.setAttribute("y2", y);
    line.setAttribute("class", "grid-line");
    svg.append(line);
    const label = document.createElementNS(namespace, "text");
    label.setAttribute("x", margin.left - 8);
    label.setAttribute("y", y + 3);
    label.setAttribute("text-anchor", "end");
    label.textContent = formatNumber(maxTemp * (1 - ratio));
    svg.append(label);
  });

  const tempPath = points.map((point, index) => `${index === 0 ? "M" : "L"}${x(point.time_hours)},${yTemp(point.temperature_celsius)}`).join(" ");
  const pressurePath = points.map((point, index) => `${index === 0 ? "M" : "L"}${x(point.time_hours)},${yPressure(point.pressure_mpa)}`).join(" ");
  svg.append(createPath(tempPath, "temperature-line"));
  svg.append(createPath(pressurePath, "pressure-line"));
  points.forEach((point) => {
    svg.append(createPoint(x(point.time_hours), yTemp(point.temperature_celsius), "temperature-point"));
    svg.append(createPoint(x(point.time_hours), yPressure(point.pressure_mpa), "pressure-point"));
  });
  elements.processChart.append(svg);
}

function createPath(path, className) {
  const namespace = "http://www.w3.org/2000/svg";
  const element = document.createElementNS(namespace, "path");
  element.setAttribute("d", path);
  element.setAttribute("class", className);
  return element;
}

function createPoint(cx, cy, className) {
  const namespace = "http://www.w3.org/2000/svg";
  const element = document.createElementNS(namespace, "circle");
  element.setAttribute("cx", cx);
  element.setAttribute("cy", cy);
  element.setAttribute("r", 3);
  element.setAttribute("class", className);
  return element;
}

function renderReport(detail) {
  const result = detail.result;
  const ansys = result?.ansys_result;
  if (!ansys) {
    elements.reportState.textContent = detail.status === "SUCCEEDED" ? "结果不可用" : "等待结果";
    elements.densityGrid.innerHTML = "";
    elements.acceptanceList.innerHTML = "";
    return;
  }
  elements.reportState.textContent = detail.simulation_status || "-";
  const density = ansys.density_distribution || {};
  const metrics = [
    ["最大变形", ansys.max_deformation, "mm"],
    ["最大应力", ansys.max_stress, "MPa"],
    ["整体致密度", ansys.final_relative_density, ""],
    ["中心区平均", density.center_region_average, ""],
    ["边缘区平均", density.edge_region_average, ""],
    ["最小/最大", `${formatNumber(density.minimum)} / ${formatNumber(density.maximum)}`, ""],
  ];
  elements.densityGrid.replaceChildren(
    ...metrics.map(([label, value, unit]) => {
      const card = document.createElement("div");
      card.className = "metric";
      const labelElement = document.createElement("div");
      labelElement.className = "metric-label";
      labelElement.textContent = label;
      const valueElement = document.createElement("div");
      valueElement.className = "metric-value";
      valueElement.textContent = formatNumber(value);
      if (unit) {
        const unitElement = document.createElement("span");
        unitElement.className = "metric-unit";
        unitElement.textContent = unit;
        valueElement.append(unitElement);
      }
      card.append(labelElement, valueElement);
      return card;
    })
  );

  const checks = result?.acceptance?.checks || [];
  if (checks.length === 0) {
    elements.acceptanceList.innerHTML = '<div class="empty">暂无验收检查</div>';
  } else {
    elements.acceptanceList.replaceChildren(
      ...checks.map((check) => {
        const row = document.createElement("div");
        row.className = "acceptance-row";
        const name = document.createElement("span");
        name.textContent = check.name;
        const value = document.createElement("span");
        value.className = check.passed ? "pass-tag" : "fail-tag";
        value.textContent = `${check.passed ? "PASS" : "FAIL"} / ${formatNumber(check.actual)} / ${formatNumber(check.limit)}`;
        row.append(name, value);
        return row;
      })
    );
  }
}

function renderArtifacts(artifacts) {
  const names = Object.keys(artifacts).sort();
  elements.artifactCount.textContent = `${names.length} 个文件`;
  if (names.length === 0) {
    elements.artifactList.innerHTML = '<div class="empty">暂无工件</div>';
    return;
  }
  elements.artifactList.replaceChildren(
    ...names.map((name) => {
      const link = document.createElement("a");
      link.className = "artifact-link";
      link.href = `/api/simulations/${state.selectedJobId}/artifacts/${encodeURIComponent(name)}`;
      const filename = document.createElement("span");
      filename.className = "filename";
      filename.textContent = name;
      const kind = document.createElement("span");
      kind.className = "kind";
      kind.textContent = name.split(".").pop();
      link.append(filename, kind);
      return link;
    })
  );
}

function renderAnsysArtifacts(jobId, names) {
  elements.ansysArtifactCount.textContent = `${names.length} 个文件`;
  if (names.length === 0) {
    elements.ansysArtifactList.innerHTML = '<div class="empty">暂无工件</div>';
    return;
  }
  elements.ansysArtifactList.replaceChildren(
    ...names.map((name) => {
      const link = document.createElement("a");
      link.className = "artifact-link";
      link.href = `/api/ansys/jobs/${jobId}/artifacts/${encodeURIComponent(name)}`;
      const filename = document.createElement("span");
      filename.className = "filename";
      filename.textContent = name;
      const kind = document.createElement("span");
      kind.className = "kind";
      kind.textContent = name.split(".").pop();
      link.append(filename, kind);
      return link;
    })
  );
}

function renderAudit() {
  elements.auditCount.textContent = `${state.audit.length} 条请求`;
  if (state.audit.length === 0) {
    elements.auditList.innerHTML = '<div class="empty">暂无下游请求审计</div>';
    elements.auditDetail.innerHTML = "";
    return;
  }
  elements.auditList.replaceChildren(
    ...state.audit.map((record) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = `audit-row${record.sequence === state.selectedAudit ? " selected" : ""}`;
      const sequence = document.createElement("span");
      sequence.textContent = `#${record.sequence}`;
      const method = document.createElement("strong");
      method.textContent = record.method;
      const url = document.createElement("span");
      url.className = "audit-url";
      url.textContent = record.url;
      const status = document.createElement("span");
      status.className = `audit-status ${record.status_code >= 400 || record.error ? "error" : "ok"}`;
      status.textContent = record.status_code ?? "ERR";
      row.append(sequence, method, url, status);
      row.addEventListener("click", () => selectAudit(record.sequence));
      return row;
    })
  );
  if (state.selectedAudit === null) {
    elements.auditDetail.innerHTML = '<div class="empty">选择一条请求查看完整请求与响应</div>';
  }
}

function renderAuditDetail(detail) {
  elements.auditDetail.replaceChildren();
  const wrapper = document.createElement("div");
  wrapper.className = "detail-grid";
  const requestBlock = document.createElement("div");
  requestBlock.className = "json-view";
  requestBlock.textContent = JSON.stringify(detail.request, null, 2);
  const responseBlock = document.createElement("div");
  responseBlock.className = "json-view";
  responseBlock.textContent = JSON.stringify(detail.response, null, 2);
  wrapper.append(requestBlock, responseBlock);
  elements.auditDetail.append(wrapper);
}

function renderEvents(events) {
  elements.eventCount.textContent = `${events.length} 条日志`;
  if (events.length === 0) {
    elements.eventList.innerHTML = '<div class="empty">暂无日志</div>';
    return;
  }
  elements.eventList.replaceChildren(
    ...events.map((event) => {
      const row = document.createElement("div");
      row.className = "event-row";
      const time = document.createElement("span");
      time.className = "event-time";
      time.textContent = formatTime(event.created_at);
      const message = document.createElement("span");
      message.className = "event-message";
      message.textContent = `[${event.status}] ${event.message}`;
      row.append(time, message);
      return row;
    })
  );
}

function showGlobalError(message) {
  elements.jobError.textContent = message;
  elements.jobError.classList.remove("hidden");
}

function statusText(status) {
  return status || "-";
}

function formatTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  return String(value);
}

function schedulePolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    if (state.activeView === "simulation") {
      await loadJobs();
      if (state.selectedJobId) await refreshDetail();
    } else {
      await loadAnsys();
    }
  }, 3000);
}

elements.uploadForm.addEventListener("submit", submitSimulation);
elements.refreshJobs.addEventListener("click", loadJobs);
elements.ansysTab.addEventListener("click", () => {
  switchView("ansys");
  loadAnsys();
});
elements.simulationTab.addEventListener("click", () => switchView("simulation"));
elements.refreshAnsys.addEventListener("click", loadAnsys);
elements.jobLogTab.addEventListener("click", () => setAnsysLogSource("job.log"));
elements.solverLogTab.addEventListener("click", () => setAnsysLogSource("job.out"));

function setAnsysLogSource(source) {
  state.ansysLogSource = source;
  elements.jobLogTab.classList.toggle("active", source === "job.log");
  elements.solverLogTab.classList.toggle("active", source === "job.out");
  loadAnsysJobDetail();
}
window.addEventListener("popstate", () => {
  const jobId = new URLSearchParams(window.location.search).get("job");
  if (jobId && jobId !== state.selectedJobId) selectJob(jobId, false);
});

function initialize() {
  loadJobs();
  loadAnsys();
  schedulePolling();
}

initialize();
