const CFG_KEY = "activeScrapeConfig";

let shouldStop = false;

function randDelay(min, ms) { return new Promise(r => setTimeout(r, min + Math.random() * (ms - min))); }

function send(action, data) {
  try { chrome.runtime.sendMessage({ action, ...(data || {}) }, () => {}); } catch (e) {}
}

async function waitEl(sel, timeout = 8000) {
  const el = document.querySelector(sel);
  if (el) return el;
  return new Promise(resolve => {
    const mo = new MutationObserver(() => {
      const f = document.querySelector(sel);
      if (f) { mo.disconnect(); resolve(f); }
    });
    mo.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => { mo.disconnect(); resolve(null); }, timeout);
  });
}

function scrollJobs() {
  const c = document.querySelector(".jobs-search-results-list, .scaffold-layout__list");
  if (c) { c.scrollTop = c.scrollHeight; } else { window.scrollBy(0, 400); }
}

function getJobIds() {
  return [...new Set(Array.from(document.querySelectorAll("[data-job-id]")).map(c => c.getAttribute("data-job-id")).filter(Boolean))];
}

function extractDetails(jobId) {
  const d = {
    job_id: jobId, date_found: new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }),
    position: "", company: "", location: "", poster_name: "", poster_title: "", poster_profile_url: "",
    job_url: "https://www.linkedin.com/jobs/view/" + jobId + "/",
    email: "", applied: "No", connection_sent: "No", notes: "", full_post: ""
  };
  try {
    const el = document.querySelector(".jobs-unified-top-card__job-title h1, .t-24.t-bold.jobs-unified-top-card__job-title");
    if (el) d.position = el.innerText.trim();
  } catch (e) {}
  try {
    const el = document.querySelector(".jobs-unified-top-card__company-name a, .jobs-unified-top-card__company-name");
    if (el) d.company = el.innerText.trim();
  } catch (e) {}
  try {
    const el = document.querySelector(".jobs-unified-top-card__bullet, .jobs-unified-top-card__workplace-type");
    if (el) d.location = el.innerText.trim();
  } catch (e) {}
  try {
    for (const b of document.querySelectorAll("button")) {
      if (b.offsetParent !== null && b.innerText.toLowerCase().includes("see more")) { b.click(); break; }
    }
  } catch (e) {}
  try {
    const desc = document.querySelector(".jobs-description-content, .jobs-box__body, main");
    if (desc) {
      const txt = desc.innerText || "";
      const emails = txt.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g) || [];
      d.email = [...new Set(emails)].filter(e => !e.includes(".png") && !e.includes(".jpg")).join(", ");
      d.full_post = txt.slice(0, 2000);
    }
  } catch (e) {}
  Object.assign(d, extractPoster());
  return d;
}

function extractPoster() {
  const r = { poster_name: "", poster_title: "", poster_profile_url: "" };
  for (const sel of [".hirer-card__hirer-information", ".jobs-poster__name", ".jobs-contact-section"]) {
    const el = document.querySelector(sel);
    if (!el) continue;
    try {
      const n = el.querySelector("a span, .jobs-poster__name, strong, b, h3");
      if (n) r.poster_name = n.innerText.trim();
    } catch (e) {}
    try {
      const t = el.querySelector(".hirer-card__hirer-job-title, .jobs-poster__subtitle, .t-14");
      if (t) r.poster_title = t.innerText.trim();
    } catch (e) {}
    try {
      const a = el.querySelector("a");
      if (a) {
        let h = a.getAttribute("href") || "";
        if (h.startsWith("/")) h = "https://www.linkedin.com" + h;
        r.poster_profile_url = h.split("?")[0];
      }
    } catch (e) {}
    if (r.poster_name) break;
  }
  return r;
}

async function clickCard(jobId) {
  const card = document.querySelector(`[data-job-id="${jobId}"]`);
  if (!card) return false;
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  await randDelay(400, 900);
  card.click();
  await randDelay(600, 1200);
  return true;
}

function buildUrl(keyword, location, config) {
  const p = new URLSearchParams();
  p.set("keywords", keyword);
  if (location) p.set("location", location);
  p.set("sortBy", "DD");
  if (config.easyApplyOnly) p.set("f_AL", "true");
  const d = config.postedWithinDays || 1;
  if (d <= 1) p.set("f_TPR", "r86400");
  else if (d <= 7) p.set("f_TPR", "r604800");
  else if (d <= 30) p.set("f_TPR", "r2592000");
  return "https://www.linkedin.com/jobs/search/?" + p.toString();
}

function matchPoster(title, targets) {
  if (!targets || !targets.length) return true;
  const l = (title || "").toLowerCase();
  return targets.some(t => l.includes(t.toLowerCase()));
}

async function nextPage(page) {
  for (const sel of [
    'button[aria-label="Page ' + (page + 1) + '"]',
    "button.artdeco-pagination__button--next:not([disabled])",
    "button.jobs-search-pagination__next-button:not([disabled])"
  ]) {
    try {
      const btn = document.querySelector(sel);
      if (btn && !btn.disabled) {
        btn.scrollIntoView({ block: "center" });
        await randDelay(300, 600);
        btn.click();
        await new Promise(r => setTimeout(r, 2500));
        return true;
      }
    } catch (e) {}
  }
  return false;
}

async function scrapePage(config, pageNum) {
  const max = config.maxJobsPerRun || 50;
  let found = 0;

  await waitEl("[data-job-id], .jobs-search-results-list", 12000);
  await randDelay(1500, 2500);

  while (found < max && !shouldStop) {
    scrollJobs();
    await randDelay(600, 1000);
    const ids = getJobIds();
    if (!ids.length) { send("log", { text: "No job card IDs found on page " + pageNum }); break; }

    send("log", { text: "Page " + pageNum + ": " + ids.length + " cards" });

    for (const id of ids) {
      if (shouldStop || found >= max) break;

      const { jobs } = await chrome.storage.local.get("jobs");
      if ((jobs || []).some(j => j.job_id === id)) { continue; }

      if (!(await clickCard(id))) { continue; }

      const det = extractDetails(id);
      if (!matchPoster(det.poster_title, config.targetPosterTitles)) { continue; }
      if (config.excludeCompanies && config.excludeCompanies.length) {
        const co = (det.company || "").toLowerCase();
        if (config.excludeCompanies.some(e => co.includes(e.toLowerCase()))) continue;
      }

      const saved = await Storage.saveJob(det);
      if (saved) { found++; send("jobFound", { job: det }); send("log", { text: "[" + found + "] " + det.position + " @ " + det.company }); }
      await randDelay(800, 2000);
    }
    if (shouldStop || found >= max) break;
    if (!(await nextPage(pageNum))) break;
    pageNum++;
  }
  return found;
}

async function runAll(config) {
  shouldStop = false;

  const qs = [];
  for (const role of config.jobRoles || []) {
    if ((config.locations || []).length) {
      for (const loc of config.locations) qs.push({ k: role, l: loc, label: role + " @ " + loc });
    } else {
      qs.push({ k: role, l: "", label: role });
    }
  }

  const saved = await chrome.storage.local.get(CFG_KEY);
  const state = saved[CFG_KEY];
  let idx = state ? state.idx : 0;
  if (!state) { await chrome.storage.local.set({ scrapeStats: { found: 0, page: 1 } }); }

  for (let i = idx; i < qs.length && !shouldStop; i++) {
    const q = qs[i];
    const url = buildUrl(q.k, q.l, config);

    await chrome.storage.local.set({ [CFG_KEY]: { idx: i, url: url, config: config, qs: qs } });
    send("log", { text: "=== " + q.label + " ===" });

    if (window.location.href !== url) {
      window.location.href = url;
      return;
    }

    const n = await scrapePage(config, 1);
    send("log", { text: "=== " + q.label + " complete: " + n + " jobs ===" });
  }

  await chrome.storage.local.remove(CFG_KEY);
  await chrome.storage.local.remove("scrapeStats");
  send("scrapingComplete", {});
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "startScraping") { runAll(msg.config || {}).catch(e => send("log", { text: "Error: " + e.message })); sendResponse({ ok: true }); return true; }
  if (msg.action === "stopScraping") { shouldStop = true; sendResponse({ ok: true }); }
  if (msg.action === "ping") { sendResponse({ ok: true }); }
});

(async function init() {
  const saved = await chrome.storage.local.get(CFG_KEY);
  const state = saved[CFG_KEY];
  if (state && state.config && window.location.href.includes("linkedin.com/jobs/search")) {
    await randDelay(500, 1000);
    send("log", { text: "Resuming session..." });
    await runAll(state.config);
  }
})();
