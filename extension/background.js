importScripts("utils/storage.js", "utils/exporter.js");

let activeTabId = null;
let pendingConfig = null;

async function getLinkedInTab() {
  const tabs = await chrome.tabs.query({ url: "https://www.linkedin.com/*" });
  if (tabs.length > 0) return tabs[0];
  const allTabs = await chrome.tabs.query({});
  const liTab = allTabs.find(t => t.url && t.url.includes("linkedin.com"));
  return liTab || null;
}

async function ensureContentPort(tabId) {
  return new Promise(resolve => {
    chrome.tabs.sendMessage(tabId, { action: "ping" }, res => {
      resolve(!!(res && res.ok));
    });
  });
}

function notifyUser(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon48.png",
    title,
    message,
  });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "log") {
    console.log(`[Content] ${msg.text}`);
    if (msg.text) msg.text = msg.text;
    sendResponse({ ok: true });
  }

  if (msg.action === "jobFound") {
    (async () => {
      const saved = await Storage.saveJob(msg.job);
      if (saved) {
        const stats = await Storage.getStats();
        chrome.runtime.sendMessage({ action: "statsUpdate", stats }).catch(() => {});
        chrome.action.setBadgeText({ text: String(stats.total) });
        chrome.action.setBadgeBackgroundColor({ color: "#0a66c2" });
      }
    })();
    sendResponse({ ok: true });
  }

  if (msg.action === "navigating") {
    activeTabId = sender.tab?.id || null;
    sendResponse({ ok: true });
  }

  if (msg.action === "scrapingComplete") {
    notifyUser("Scraping Complete", "All job searches finished.");
    pendingConfig = null;
    chrome.runtime.sendMessage({ action: "scrapingComplete" }).catch(() => {});
    sendResponse({ ok: true });
  }

  return true;
});

chrome.action.onClicked.addListener(() => {
  chrome.runtime.openOptionsPage();
});

async function startScraping(config) {
  const tab = await getLinkedInTab();
  if (!tab) {
    notifyUser("LinkedIn Required", "Open a LinkedIn tab first.");
    return;
  }

  activeTabId = tab.id;
  pendingConfig = config;

  const accessible = await ensureContentPort(tab.id);
  if (!accessible) {
    notifyUser("Reload LinkedIn", "Please refresh LinkedIn for the extension to load.");
    return;
  }

  await Storage.setState({
    status: "scraping",
    currentQueryIndex: 0,
    currentPage: 1,
    totalFound: 0,
  });

  chrome.tabs.sendMessage(tab.id, { action: "startScraping", config }).catch(() => {});
  notifyUser("Scraping Started", `Searching ${config.jobRoles.length} roles × ${config.locations.length} locations`);
}

async function stopScraping() {
  if (activeTabId) {
    chrome.tabs.sendMessage(activeTabId, { action: "stopScraping" }).catch(() => {});
  }
  pendingConfig = null;
  await Storage.setState({ status: "idle", currentQueryIndex: 0, currentPage: 1, totalFound: 0 });
  notifyUser("Scraping Stopped", "The scraper has been stopped.");
}

chrome.runtime.onConnect.addListener(port => {
  if (port.name === "popup") {
    port.onMessage.addListener(async msg => {
      if (msg.action === "startScraping") {
        await startScraping(msg.config);
        port.postMessage({ action: "started" });
      }
      if (msg.action === "stopScraping") {
        await stopScraping();
        port.postMessage({ action: "stopped" });
      }
      if (msg.action === "getState") {
        const state = await Storage.getState();
        const stats = await Storage.getStats();
        port.postMessage({ action: "state", state, stats });
      }
    });
  }

  if (port.name === "dashboard") {
    port.onMessage.addListener(async msg => {
      if (msg.action === "startScraping") {
        await startScraping(msg.config);
      }
      if (msg.action === "stopScraping") {
        await stopScraping();
      }
      if (msg.action === "getState") {
        const state = await Storage.getState();
        const stats = await Storage.getStats();
        port.postMessage({ action: "state", state, stats });
      }
      if (msg.action === "getJobs") {
        const jobs = await Storage.getJobs();
        port.postMessage({ action: "jobs", jobs });
      }
      if (msg.action === "exportCSV") {
        const jobs = await Storage.getJobs();
        Exporter.downloadCSV(jobs);
      }
      if (msg.action === "exportXLS") {
        const jobs = await Storage.getJobs();
        Exporter.downloadXLS(jobs);
      }
      if (msg.action === "clearJobs") {
        await chrome.storage.local.set({ jobs: [] });
        await Storage.setState({ status: "idle", currentQueryIndex: 0, currentPage: 1, totalFound: 0 });
        port.postMessage({ action: "cleared" });
      }
      if (msg.action === "getPreferences") {
        const prefs = await Storage.getPreferences();
        port.postMessage({ action: "preferences", prefs });
      }
      if (msg.action === "savePreferences") {
        await Storage.savePreferences(msg.prefs);
        port.postMessage({ action: "preferencesSaved" });
      }
    });
  }
});
