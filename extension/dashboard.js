let port = null;

function connect() {
  port = chrome.runtime.connect({ name: "dashboard" });
  port.onMessage.addListener(handleMessage);
}

function handleMessage(msg) {
  if (msg.action === "state") updateState(msg.state, msg.stats);
  if (msg.action === "jobs") renderJobs(msg.jobs);
  if (msg.action === "preferences") populateForm(msg.prefs);
  if (msg.action === "preferencesSaved") {
    document.getElementById("saveStatus").textContent = "Saved!";
    setTimeout(() => document.getElementById("saveStatus").textContent = "", 2000);
  }
  if (msg.action === "cleared") {
    renderJobs([]);
    updateState({ status: "idle" }, { total: 0, applied: 0, connected: 0 });
  }
}

function updateState(state, stats) {
  const isScraping = state.status === "scraping";
  document.getElementById("btnStart").style.display = isScraping ? "none" : "inline-block";
  document.getElementById("btnStop").style.display = isScraping ? "inline-block" : "none";

  if (stats) {
    document.getElementById("dashTotal").textContent = stats.total;
    document.getElementById("dashApplied").textContent = stats.applied;
    document.getElementById("dashConnected").textContent = stats.connected;
    chrome.action.setBadgeText({ text: String(stats.total) });
  }
}

function populateForm(prefs) {
  document.getElementById("jobRoles").value = (prefs.jobRoles || []).join("\n");
  document.getElementById("locations").value = (prefs.locations || []).join("\n");
  document.getElementById("excludeCompanies").value = (prefs.excludeCompanies || []).join("\n");
  document.getElementById("easyApplyOnly").checked = prefs.easyApplyOnly !== false;
  document.getElementById("postedWithinDays").value = prefs.postedWithinDays || 1;
  document.getElementById("maxJobsPerRun").value = prefs.maxJobsPerRun || 50;
}

function getFormPrefs() {
  return {
    jobRoles: document.getElementById("jobRoles").value.split("\n").map(s => s.trim()).filter(Boolean),
    locations: document.getElementById("locations").value.split("\n").map(s => s.trim()).filter(Boolean),
    excludeCompanies: document.getElementById("excludeCompanies").value.split("\n").map(s => s.trim()).filter(Boolean),
    easyApplyOnly: document.getElementById("easyApplyOnly").checked,
    postedWithinDays: parseInt(document.getElementById("postedWithinDays").value) || 1,
    maxJobsPerRun: parseInt(document.getElementById("maxJobsPerRun").value) || 50,
    targetPosterTitles: [],
    excludedKeywords: [],
  };
}

function renderJobs(jobs) {
  const tbody = document.getElementById("jobsBody");
  const empty = document.getElementById("emptyMsg");
  tbody.innerHTML = "";

  if (!jobs.length) {
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  const recent = jobs.slice().reverse();
  recent.forEach(j => {
    const tr = document.createElement("tr");
    const cells = [
      j.position, j.company, j.location,
      j.poster_name ? `${j.poster_name}${j.poster_title ? " - " + j.poster_title : ""}` : "-",
      j.date_found || "-",
      j.applied === "Yes" ? "✓" : "-",
      j.connection_sent === "Yes" ? "✓" : "-",
      j.email || "-",
    ];
    cells.forEach(t => {
      const td = document.createElement("td");
      td.textContent = t || "-";
      td.title = t || "";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  connect();

  const state = await Storage.getState();
  const stats = await Storage.getStats();
  updateState(state, stats);

  if (port) port.postMessage({ action: "getPreferences" });
  if (port) port.postMessage({ action: "getJobs" });

  document.getElementById("btnStart").addEventListener("click", () => {
    const prefs = getFormPrefs();
    if (port) port.postMessage({ action: "startScraping", config: prefs });
  });

  document.getElementById("btnStop").addEventListener("click", () => {
    if (port) port.postMessage({ action: "stopScraping" });
  });

  document.getElementById("btnSavePrefs").addEventListener("click", () => {
    const prefs = getFormPrefs();
    if (port) port.postMessage({ action: "savePreferences", prefs });
  });

  document.getElementById("btnExportCSV").addEventListener("click", () => {
    if (port) port.postMessage({ action: "exportCSV" });
  });

  document.getElementById("btnExportXLS").addEventListener("click", () => {
    if (port) port.postMessage({ action: "exportXLS" });
  });

  document.getElementById("btnClear").addEventListener("click", () => {
    if (confirm("Delete all tracked jobs?")) {
      if (port) port.postMessage({ action: "clearJobs" });
    }
  });
});
