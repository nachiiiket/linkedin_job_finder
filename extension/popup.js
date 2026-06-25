let port = null;

function connect() {
  port = chrome.runtime.connect({ name: "popup" });
  port.onMessage.addListener(handleMessage);
  port.onDisconnect.addListener(() => { port = null; });
}

function handleMessage(msg) {
  if (msg.action === "state") updateUI(msg.state, msg.stats);
  if (msg.action === "started") setStatus("scraping");
  if (msg.action === "stopped") setStatus("idle");
}

function updateUI(state, stats) {
  const statusEl = document.getElementById("statusText");
  if (state.status === "scraping") {
    statusEl.textContent = "Scraping...";
    statusEl.className = "status-scraping";
  } else {
    statusEl.textContent = "Idle";
    statusEl.className = "status-idle";
  }

  document.getElementById("statTotal").textContent = stats.total;
  document.getElementById("statApplied").textContent = stats.applied;
  document.getElementById("statConnected").textContent = stats.connected;

  document.getElementById("btnStart").style.display = state.status === "scraping" ? "none" : "block";
  document.getElementById("btnStop").style.display = state.status === "scraping" ? "block" : "none";
}

function setStatus(s) {
  const el = document.getElementById("statusText");
  if (s === "scraping") {
    el.textContent = "Scraping...";
    el.className = "status-scraping";
    document.getElementById("btnStart").style.display = "none";
    document.getElementById("btnStop").style.display = "block";
  } else {
    el.textContent = "Idle";
    el.className = "status-idle";
    document.getElementById("btnStart").style.display = "block";
    document.getElementById("btnStop").style.display = "none";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  connect();

  const state = await Storage.getState();
  const stats = await Storage.getStats();
  updateUI(state, stats);

  const prefs = await Storage.getPreferences();

  document.getElementById("btnStart").addEventListener("click", () => {
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
  if (msg.action === "scrapingComplete") {
    setStatus("idle");
  }
  if (msg.action === "log") {
    const logList = document.getElementById("logList");
    const entry = document.createElement("div");
    entry.className = "log-entry";
    entry.textContent = msg.text;
    logList.appendChild(entry);
    logList.scrollTop = logList.scrollHeight;
  }
});
