let port = null;
function connect() { port = chrome.runtime.connect({ name: "dashboard" }); port.onMessage.addListener(handle); }

function handle(msg) {
  if (msg.action === "state") updateState(msg.state, msg.stats);
  if (msg.action === "jobs") renderJobs(msg.jobs);
  if (msg.action === "preferences") populateForm(msg.prefs);
  if (msg.action === "preferencesSaved") { document.getElementById("saveStatus").textContent = "Saved!"; setTimeout(() => document.getElementById("saveStatus").textContent = "", 2000); }
  if (msg.action === "cleared") { renderJobs([]); updateState({ status: "idle" }, { total: 0, applied: 0, connected: 0 }); }
}

function updateState(state, stats) {
  const s = state.status === "scraping";
  document.getElementById("btnStart").style.display = s ? "none" : "inline-block";
  document.getElementById("btnStop").style.display = s ? "inline-block" : "none";
  document.getElementById("dashSearchMode").disabled = s;
  if (state.mode === "posts") document.getElementById("dashSearchMode").value = "posts";
  else if (state.mode === "both") document.getElementById("dashSearchMode").value = "both";
  else document.getElementById("dashSearchMode").value = "jobs";
  if (stats) {
    document.getElementById("dashTotal").textContent = stats.total;
    document.getElementById("dashApplied").textContent = stats.applied;
    document.getElementById("dashConnected").textContent = stats.connected;
    chrome.action.setBadgeText({ text: String(stats.total) });
  }
}

function populateForm(p) {
  document.getElementById("jobRoles").value = (p.jobRoles || []).join("\n");
  document.getElementById("locations").value = (p.locations || []).join("\n");
  document.getElementById("excludeCompanies").value = (p.excludeCompanies || []).join("\n");
  document.getElementById("easyApplyOnly").checked = p.easyApplyOnly !== false;
  document.getElementById("postedWithinDays").value = p.postedWithinDays || 1;
  document.getElementById("maxJobsPerRun").value = p.maxJobsPerRun || 50;
}

function getPrefs() {
  return {
    jobRoles: document.getElementById("jobRoles").value.split("\n").map(s => s.trim()).filter(Boolean),
    locations: document.getElementById("locations").value.split("\n").map(s => s.trim()).filter(Boolean),
    excludeCompanies: document.getElementById("excludeCompanies").value.split("\n").map(s => s.trim()).filter(Boolean),
    easyApplyOnly: document.getElementById("easyApplyOnly").checked,
    postedWithinDays: parseInt(document.getElementById("postedWithinDays").value) || 1,
    maxJobsPerRun: parseInt(document.getElementById("maxJobsPerRun").value) || 50,
    targetPosterTitles: [], excludedKeywords: [],
    searchMode: document.getElementById("dashSearchMode").value,
  };
}

function renderJobs(jobs) {
  const tb = document.getElementById("jobsBody"); const em = document.getElementById("emptyMsg"); tb.innerHTML = "";
  if (!jobs.length) { em.style.display = "block"; return; }
  em.style.display = "none";
  jobs.slice().reverse().forEach(j => {
    const tr = document.createElement("tr");
    [j.position, j.company, j.location, j.poster_name ? j.poster_name + (j.poster_title ? " - " + j.poster_title : "") : "-", j.email || "-", j.date_found || "-"].forEach(t => {
      const td = document.createElement("td"); td.textContent = t || "-"; td.title = t || ""; tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  connect();
  const s = await Storage.getState(); const st = await Storage.getStats();
  updateState(s, st);
  if (port) port.postMessage({ action: "getPreferences" });
  if (port) port.postMessage({ action: "getJobs" });

  document.getElementById("btnStart").addEventListener("click", () => { const p = getPrefs(); if (port) port.postMessage({ action: "startScraping", config: p }); });
  document.getElementById("btnStop").addEventListener("click", () => { if (port) port.postMessage({ action: "stopScraping" }); });
  document.getElementById("btnSavePrefs").addEventListener("click", () => { const p = getPrefs(); if (port) port.postMessage({ action: "savePreferences", prefs: p }); });
  document.getElementById("btnExportCSV").addEventListener("click", () => { if (port) port.postMessage({ action: "exportCSV" }); });
  document.getElementById("btnExportXLS").addEventListener("click", () => { if (port) port.postMessage({ action: "exportXLS" }); });
  document.getElementById("btnClear").addEventListener("click", () => { if (confirm("Delete all?")) { if (port) port.postMessage({ action: "clearJobs" }); } });
});
