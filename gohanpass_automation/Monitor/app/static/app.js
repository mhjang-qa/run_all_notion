const state = {
  timer: null,
};

const fmt = new Intl.DateTimeFormat("ko-KR", {
  dateStyle: "short",
  timeStyle: "medium",
});

async function api(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function dateText(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : fmt.format(date);
}

function renderKpis(kpi, source) {
  const latestVersion = source === "notion" ? kpi.latestVersion : "sample";
  const latestVersionHint = source === "notion" ? "마지막 기록 기준" : "실제 Raw data 아님";
  const cards = [
    ["총 실행", kpi.runs, `최근 ${kpi.runs}건 기준`],
    ["통과율", `${kpi.passRate}%`, `PASS ${kpi.pass}`],
    ["실패율", `${kpi.failRate}%`, `FAIL ${kpi.fail}`],
    ["실패 실행", kpi.failedRuns, "실패가 있었던 실행 수"],
    ["최신 버전", latestVersion, latestVersionHint],
    ["현재 상태", statusLabel(kpi.latestStatus), "가장 최근 실행"],
  ];

  document.querySelector("#kpis").innerHTML = cards
    .map(([label, value, hint]) => `
      <article class="kpi">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
        <small>${escapeHtml(hint)}</small>
      </article>
    `)
    .join("");
}

function statusLabel(status) {
  return {
    passed: "정상",
    failed: "확인 필요",
    running: "실행중",
    unknown: "대기",
  }[status] || status || "-";
}

function renderCurrent(current, source) {
  const statusText =
    current.mode === "running"
      ? "실행중"
      : current.mode === "attention"
        ? "확인 필요"
        : "정상";
  const sourceMessage = source === "notion"
    ? "Notion Raw data 기준"
    : "현재는 샘플 데이터 표시중";
  const headline =
    current.mode === "running"
      ? "go.hanpass 실행중"
      : "go.hanpass 최근 결과";

  document.querySelector("#currentStatus").innerHTML = `
    <div class="status-card">
      <div class="status-band">
        <span class="badge ${escapeHtml(current.mode === "attention" ? "failed" : current.mode)}">${escapeHtml(statusText)}</span>
        <span class="meta">${escapeHtml(sourceMessage)}</span>
      </div>
      <div class="status-body">
        <strong class="status-title">${escapeHtml(headline)}</strong>
        <p class="status-summary">${escapeHtml(current.message)}</p>
        <p class="meta">리포트: ${escapeHtml(current.title)}</p>
        <div class="status-metrics">
          <div class="metric-chip">
            <span class="meta">버전</span>
            <strong>${escapeHtml(current.version || "-")}</strong>
          </div>
          <div class="metric-chip">
            <span class="meta">상태</span>
            <strong>${escapeHtml(statusText)}</strong>
          </div>
          <div class="metric-chip">
            <span class="meta">기준 시각</span>
            <strong>${escapeHtml(dateText(current.startedAt))}</strong>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderRecentFailures(items) {
  const target = document.querySelector("#recentFailures");
  const visibleItems = items.slice(0, 3);
  if (!visibleItems.length) {
    target.innerHTML = `<div class="empty">최근 실패 항목 없음</div>`;
    return;
  }
  target.innerHTML = visibleItems.map((item) => `
    <div class="item">
      <strong>${escapeHtml(item.scenario)} / ${escapeHtml(item.name)}</strong>
      <p class="meta">${escapeHtml(item.version)} · ${escapeHtml(dateText(item.createdAt))}</p>
      <p class="meta">상태: ${escapeHtml(item.status)}</p>
      ${item.url ? `<a class="meta" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">Notion row 열기</a>` : ""}
    </div>
  `).join("");
}

function renderRepeatFailures(items) {
  const target = document.querySelector("#repeatFailures");
  const visibleItems = items.slice(0, 3);
  if (!visibleItems.length) {
    target.innerHTML = `<div class="empty">반복 실패 없음</div>`;
    return;
  }
  target.innerHTML = visibleItems.map((item) => `
    <div class="item">
      <strong>${escapeHtml(item.scenario)} / ${escapeHtml(item.name)}</strong>
      <p class="meta">같은 실패 ${escapeHtml(item.count)}회 · 최근 ${escapeHtml(dateText(item.latestAt))}</p>
    </div>
  `).join("");
}

function renderSnapshot(snapshot) {
  const target = document.querySelector("#latestSnapshot");
  const panel = document.querySelector(".snapshot-panel");
  if (!snapshot) {
    panel.classList.add("is-hidden");
    target.innerHTML = "";
    return;
  }
  panel.classList.remove("is-hidden");
  target.innerHTML = `
    <div class="snapshot-box">
      <img src="${escapeHtml(snapshot.url)}" alt="latest snapshot" />
    </div>
    <p class="meta">${escapeHtml(snapshot.title)} · ${escapeHtml(snapshot.version)} · ${escapeHtml(dateText(snapshot.createdAt))}</p>
  `;
}

function renderVersions(items) {
  const target = document.querySelector("#versions");
  const visibleItems = items.slice(0, 3);
  if (!visibleItems.length) {
    target.innerHTML = `<div class="empty">버전 데이터 없음</div>`;
    return;
  }
  target.innerHTML = visibleItems.map((item) => `
    <div class="item">
      <div class="status-line">
        <strong>${escapeHtml(item.version)}</strong>
        <span class="badge ${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span>
      </div>
      <p class="meta">실행 ${escapeHtml(item.runs)}건 · 통과율 ${escapeHtml(item.passRate)}% · FAIL ${escapeHtml(item.failed)}</p>
      <p class="meta">최근 ${escapeHtml(dateText(item.latestAt))}</p>
    </div>
  `).join("");
}

function renderRows(runs) {
  const visibleRuns = runs.slice(0, 3);
  document.querySelector("#runRows").innerHTML = visibleRuns.map((run) => `
    <tr>
      <td>${escapeHtml(dateText(run.createdAt))}</td>
      <td>${escapeHtml(run.version)}</td>
      <td><span class="badge ${escapeHtml(run.status)}">${escapeHtml(statusLabel(run.status))}</span></td>
      <td>${escapeHtml(run.pass)}</td>
      <td>${escapeHtml(run.fail)}</td>
      <td>${escapeHtml(run.total)}</td>
      <td>${run.url ? `<a href="${escapeHtml(run.url)}" target="_blank" rel="noreferrer">${escapeHtml(run.title)}</a>` : escapeHtml(run.title)}</td>
    </tr>
  `).join("");
}

async function refresh(force = false) {
  const data = await api(`/api/monitor${force ? "?force=true" : ""}`);
  const badge = document.querySelector("#sourceBadge");
  badge.textContent = data.source === "notion" ? "Notion Live" : "샘플 데이터";
  badge.classList.toggle("sample", data.source !== "notion");
  document.querySelector("#updatedAt").textContent = dateText(data.updatedAt);
  if (data.error) {
    badge.title = data.error;
  }

  renderKpis(data.kpi, data.source);
  renderCurrent(data.current, data.source);
  renderRecentFailures(data.recentFailures);
  renderRepeatFailures(data.repeatFailures);
  renderSnapshot(data.latestSnapshot);
  renderVersions(data.versions);
  renderRows(data.runs);
}

document.querySelector("#refreshBtn").addEventListener("click", () => {
  refresh(true).catch((error) => {
    document.querySelector("#currentStatus").innerHTML = `<pre>${escapeHtml(error.message)}</pre>`;
  });
});

refresh().catch((error) => {
  document.querySelector("#currentStatus").innerHTML = `<pre>${escapeHtml(error.message)}</pre>`;
});

state.timer = window.setInterval(() => refresh().catch(() => {}), 30000);
