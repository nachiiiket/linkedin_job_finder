let port = null;

function connect() {
  port = chrome.runtime.connect({ name: "popup" });
  port.onMessage.addListener(m => {
    if (m.action === "state") updateUI(m.state, m.stats);
    if (m.action === "started") setStatus("scraping");
    if (m.action === "stopped") setStatus("idle");
  });
  port.onDisconnect.addListener(() => { port = null; });
}

function updateUI(state, stats) {
  document.getElementById("statusText").textContent = state.status === "scraping" ? "Scraping..." : "Idle";
  document.getElementById("statusText").className = state.status === "scraping" ? "status-scraping" : "status-idle";
  document.getElementById("statTotal").textContent = (stats || {}).total || 0;
  document.getElementById("statApplied").textContent = (stats || {}).applied || 0;
  document.getElementById("statConnected").textContent = (stats || {}).connected || 0;
  document.getElementById("btnStart").style.display = state.status === "scraping" ? "none" : "block";
  document.getElementById("btnStop").style.display = state.status === "scraping" ? "block" : "none";
  document.getElementById("searchMode").disabled = state.status === "scraping";
  if (state.mode === "posts") document.getElementById("searchMode").value = "posts";
  else if (state.mode === "both") document.getElementById("searchMode").value = "both";
  else document.getElementById("searchMode").value = "jobs";
}

function setStatus(s) {
  document.getElementById("statusText").textContent = s === "scraping" ? "Scraping..." : "Idle";
  document.getElementById("statusText").className = s === "scraping" ? "status-scraping" : "status-idle";
  document.getElementById("btnStart").style.display = s === "scraping" ? "none" : "block";
  document.getElementById("btnStop").style.display = s === "scraping" ? "block" : "none";
  document.getElementById("searchMode").disabled = s === "scraping";
}

document.addEventListener("DOMContentLoaded", async () => {
  connect();
  const state = await Storage.getState();
  const stats = await Storage.getStats();
  updateUI(state, stats);
  const prefs = await Storage.getPreferences();

  document.getElementById("btnStart").addEventListener("click", () => {
    prefs.searchMode = document.getElementById("searchMode").value;
    if (port) port.postMessage({ action: "startScraping", config: prefs });
  });
  document.getElementById("btnStop").addEventListener("click", () => {
    if (port) port.postMessage({ action: "stopScraping" });
  });
  document.getElementById("btnDashboard").addEventListener("click", () => {
    chrome.tabs.create({ url: "dashboard.html" });
  });
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === "statsUpdate") {
    document.getElementById("statTotal").textContent = msg.stats.total;
    document.getElementById("statApplied").textContent = msg.stats.applied;
    document.getElementById("statConnected").textContent = msg.stats.connected;
    chrome.action.setBadgeText({ text: String(msg.stats.total) });
  }
  if (msg.action === "scrapingComplete") setStatus("idle");
  if (msg.action === "log") {
    const el = document.getElementById("logList");
    const d = document.createElement("div"); d.className = "log-entry"; d.textContent = msg.text;
    el.appendChild(d); el.scrollTop = el.scrollHeight;
  }
});
