let shouldStop = false;

function rand(lo, hi) { return new Promise(r => setTimeout(r, lo + Math.random() * (hi - lo))); }
function send(a, d) { try { chrome.runtime.sendMessage({ action: a, ...(d || {}) }, () => {}); } catch (e) {} }

function waitEl(sel, t) {
  const el = document.querySelector(sel); if (el) return el;
  return new Promise(r => {
    const mo = new MutationObserver(() => { const f = document.querySelector(sel); if (f) { mo.disconnect(); r(f); } });
    mo.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => { mo.disconnect(); r(null); }, t || 8000);
  });
}

/* ====== JOBS SEARCH ====== */

function jobsUrl(kw, loc, cfg) {
  const p = new URLSearchParams();
  p.set("keywords", kw); if (loc) p.set("location", loc);
  p.set("sortBy", "DD");
  if (cfg.easyApplyOnly) p.set("f_AL", "true");
  const d = cfg.postedWithinDays || 1; p.set("f_TPR", d <= 1 ? "r86400" : d <= 7 ? "r604800" : "r2592000");
  return "https://www.linkedin.com/jobs/search/?" + p;
}

function getJobIds() {
  return [...new Set(Array.from(document.querySelectorAll("[data-job-id]")).map(c => c.getAttribute("data-job-id")).filter(Boolean))];
}

function scrollJobs() {
  const c = document.querySelector(".jobs-search-results-list, .scaffold-layout__list");
  if (c) c.scrollTop = c.scrollHeight; else window.scrollBy(0, 400);
}

async function clickCard(jid) {
  const card = document.querySelector(`[data-job-id="${jid}"]`);
  if (!card) return false;
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  await rand(400, 900);
  card.click(); await rand(600, 1200);
  return true;
}

function extractJob(jid) {
  const d = { job_id: jid, date_found: new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }),
    position: "", company: "", location: "", poster_name: "", poster_title: "", poster_profile_url: "",
    job_url: "https://www.linkedin.com/jobs/view/" + jid + "/", email: "", applied: "No", connection_sent: "No", notes: "", full_post: "" };
  try { const e = document.querySelector(".jobs-unified-top-card__job-title h1, .t-24.t-bold.jobs-unified-top-card__job-title"); if (e) d.position = e.innerText.trim(); } catch(e) {}
  try { const e = document.querySelector(".jobs-unified-top-card__company-name a, .jobs-unified-top-card__company-name"); if (e) d.company = e.innerText.trim(); } catch(e) {}
  try { const e = document.querySelector(".jobs-unified-top-card__bullet, .jobs-unified-top-card__workplace-type"); if (e) d.location = e.innerText.trim(); } catch(e) {}
  try { for (const b of document.querySelectorAll("button")) { if (b.offsetParent !== null && b.innerText.toLowerCase().includes("see more")) { b.click(); break; } } } catch(e) {}
  try {
    const desc = document.querySelector(".jobs-description-content, .jobs-box__body, main");
    if (desc) { const t = desc.innerText || ""; const emails = t.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g) || []; d.email = [...new Set(emails)].filter(e => !e.includes(".png") && !e.includes(".jpg")).join(", "); d.full_post = t.slice(0, 2000); }
  } catch(e) {}
  Object.assign(d, posterInfo());
  return d;
}

function posterInfo() {
  const r = { poster_name: "", poster_title: "", poster_profile_url: "" };
  for (const sel of [".hirer-card__hirer-information", ".jobs-poster__name", ".jobs-contact-section"]) {
    const el = document.querySelector(sel); if (!el) continue;
    try { const n = el.querySelector("a span, .jobs-poster__name, strong, b, h3"); if (n) r.poster_name = n.innerText.trim(); } catch(e) {}
    try { const t = el.querySelector(".hirer-card__hirer-job-title, .jobs-poster__subtitle, .t-14"); if (t) r.poster_title = t.innerText.trim(); } catch(e) {}
    try { const a = el.querySelector("a"); if (a) { let h = a.getAttribute("href") || ""; if (h.startsWith("/")) h = "https://www.linkedin.com" + h; r.poster_profile_url = h.split("?")[0]; } } catch(e) {}
    if (r.poster_name) break;
  }
  return r;
}

async function nextJobPage(pg) {
  for (const sel of ['button[aria-label="Page ' + (pg + 1) + '"]', "button.artdeco-pagination__button--next:not([disabled])", "button.jobs-search-pagination__next-button:not([disabled])"]) {
    try {
      const btn = document.querySelector(sel);
      if (btn && !btn.disabled) { btn.scrollIntoView({ block: "center" }); await rand(300, 600); btn.click(); await new Promise(r => setTimeout(r, 2500)); return true; }
    } catch(e) {}
  }
  return false;
}

async function scrapeJobs(cfg) {
  const max = cfg.maxJobsPerRun || 50;
  await waitEl("[data-job-id], .jobs-search-results-list", 12000);
  await rand(1500, 2500);
  let found = 0, pg = 1;

  while (found < max && !shouldStop) {
    scrollJobs(); await rand(600, 1000);
    const ids = getJobIds();
    if (!ids.length) { send("log", { text: "No job cards on page " + pg }); break; }
    send("log", { text: "Jobs Page " + pg + ": " + ids.length + " cards" });

    for (const id of ids) {
      if (shouldStop || found >= max) break;
      const { jobs } = await chrome.storage.local.get("jobs");
      if ((jobs || []).some(j => j.job_id === id)) continue;
      if (!(await clickCard(id))) continue;
      const det = extractJob(id);
      if (cfg.excludeCompanies && cfg.excludeCompanies.length) {
        if (cfg.excludeCompanies.some(e => (det.company || "").toLowerCase().includes(e.toLowerCase()))) continue;
      }
      const saved = await Storage.saveJob(det);
      if (saved) { found++; send("jobFound", { job: det }); }
      await rand(800, 2000);
    }
    if (shouldStop || found >= max) break;
    if (!(await nextJobPage(pg))) break;
    pg++;
  }
  return found;
}

/* ====== POSTS SEARCH ====== */

function postsUrl(query) {
  return "https://www.linkedin.com/search/results/content/?keywords=" + encodeURIComponent(query) + "&origin=GLOBAL_SEARCH_HEADER&sortBy=%22date_posted%22&f_TPR=r86400";
}

function generateQueries(roles) {
  const qs = [];
  for (const role of roles) qs.push({ query: '"Hiring" AND "' + role + '"', label: role, role: role });
  return qs;
}

function clickSeeMore(el) {
  for (const b of el.querySelectorAll("button, span[role='button']")) {
    const t = (b.textContent || "").trim().toLowerCase();
    if (["see more", "…more", "...more", "show more"].includes(t)) { b.click(); }
  }
}

function extractPostMeta(el) {
  let profileUrl = "", dateText = "";
  for (const a of el.querySelectorAll('a[href*="/in/"]')) {
    const h = a.href || "";
    if (h.includes("/in/") && !h.includes("/feed/")) { profileUrl = h.split("?")[0]; break; }
  }
  const timeEl = el.querySelector("time");
  if (timeEl) dateText = (timeEl.getAttribute("datetime") || timeEl.textContent || "").trim();
  if (!dateText) { const sp = el.querySelector(".feed-shared-actor__sub-description"); if (sp) dateText = sp.textContent.trim(); }
  return { profileUrl, dateText };
}

function extractPosterFromFeed(el) {
  const r = { poster_name: "", poster_title: "", poster_profile_url: "" };
  const actor = el.querySelector(".feed-shared-actor__name, .update-components-actor__name, a[href*='/in/']");
  if (actor) {
    const spans = actor.querySelectorAll("span[dir='ltr'], span[dir='auto']");
    r.poster_name = Array.from(spans).map(s => s.textContent.trim()).filter(Boolean).join(" ") || actor.textContent.trim();
    r.poster_profile_url = actor.getAttribute("href") || "";
    if (r.poster_profile_url.startsWith("/")) r.poster_profile_url = "https://www.linkedin.com" + r.poster_profile_url;
    r.poster_profile_url = r.poster_profile_url.split("?")[0];
  }
  const titleEl = el.querySelector(".feed-shared-actor__description, .update-components-actor__subtitle");
  if (titleEl) r.poster_title = titleEl.textContent.trim();
  return r;
}

function extractPostText(el) {
  const textEl = el.querySelector(".feed-shared-text__text-view, .update-components-text, .feed-shared-update-v2__description, .search-result__content");
  if (textEl) {
    const cloned = textEl.cloneNode(true);
    for (const s of cloned.querySelectorAll("button, .visually-hidden, [aria-hidden='true']")) s.remove();
    return cloned.textContent.trim();
  }
  return "";
}

async function scrapePosts(cfg) {
  const max = cfg.maxJobsPerRun || 50;
  await waitEl(".feed-shared-update-v2, [data-urn*='activity'], li.reusable-search__result-container, .search-content__result", 12000);
  await rand(1500, 2500);
  let found = 0;

  const getPosts = () => {
    for (const sel of [".feed-shared-update-v2", "[data-urn*='activity']", "li.reusable-search__result-container", ".search-content__result"]) {
      const els = document.querySelectorAll(sel);
      if (els.length >= 2) return Array.from(els);
    }
    return [];
  };

  while (found < max && !shouldStop) {
    scrollJobs(); await rand(1000, 1500);
    const els = getPosts();
    send("log", { text: "Found " + els.length + " posts on page" });

    for (const el of els) {
      if (shouldStop || found >= max) break;

      clickSeeMore(el);
      await rand(200, 400);

      const text = (el.innerText || "").trim();
      if (text.length < 80) continue;

      const meta = extractPostMeta(el);
      const poster = extractPosterFromFeed(el);
      const parsed = LinkedinParser.parsePost(text, meta.profileUrl || poster.poster_profile_url, meta.dateText, "");

      if (!parsed) continue;
      if (!parsed.poster_name && !parsed.email) continue;

      Object.assign(parsed, poster);

      const saved = await Storage.saveJob(parsed);
      if (saved) {
        found++;
        send("jobFound", { job: parsed });
        send("log", { text: "[" + found + "] Post: " + (parsed.poster_name || "?") + (parsed.email ? " - " + parsed.email : "") + (parsed.company ? " @ " + parsed.company : "") });
      }
      await rand(500, 1200);
    }

    scrollJobs();
    await rand(2000, 3000);
  }
  return found;
}

/* ====== MAIN ====== */

function buildPhaseQueries(cfg, phase) {
  const qs = [];
  if (phase === "posts") {
    for (const role of cfg.jobRoles || []) qs.push({ keyword: role, location: "", label: "Posts: " + role, query: '"Hiring" AND "' + role + '"', _posts: true });
  } else {
    for (const role of cfg.jobRoles || []) {
      if ((cfg.locations || []).length) { for (const loc of cfg.locations) qs.push({ keyword: role, location: loc, label: "Jobs: " + role + " @ " + loc, _posts: false }); }
      else { qs.push({ keyword: role, location: "", label: "Jobs: " + role, _posts: false }); }
    }
  }
  return qs;
}

async function runPhase(cfg, phase, startIdx) {
  const queries = buildPhaseQueries(cfg, phase);
  const scraper = phase === "posts" ? scrapePosts : scrapeJobs;

  for (let i = startIdx; i < queries.length && !shouldStop; i++) {
    const q = queries[i];
    const url = q._posts ? postsUrl(q.query) : jobsUrl(q.keyword, q.location, cfg);

    await chrome.storage.local.set({ activeScrapeConfig: { phase, idx: i, url, config: cfg } });
    send("log", { text: "=== " + q.label + " ===" });

    if (window.location.href !== url) { window.location.href = url; return; }

    const found = await scraper(cfg);
    send("log", { text: "=== Complete: " + found + " items ===" });
  }
  return true;
}

async function runAll(cfg) {
  const state = await Storage.getState();
  if (state.stopRequested) { await chrome.storage.local.remove("activeScrapeConfig"); return; }

  const mode = cfg.searchMode || "jobs";
  const phases = mode === "both" ? ["jobs", "posts"] : [mode === "posts" ? "posts" : "jobs"];

  const saved = await chrome.storage.local.get("activeScrapeConfig");
  let sc = saved.activeScrapeConfig;
  let phaseStart = sc ? phases.indexOf(sc.phase) : 0;
  if (phaseStart < 0) phaseStart = 0;

  await Storage.setState({ status: "scraping", mode, totalFound: 0 });

  for (let p = phaseStart; p < phases.length && !shouldStop; p++) {
    const phase = phases[p];
    const idx = (sc && sc.phase === phase) ? (sc.idx || 0) : 0;
    const done = await runPhase(cfg, phase, idx);
    if (!done) return;
    sc = null;
  }

  await chrome.storage.local.remove("activeScrapeConfig");
  await Storage.setState({ status: "idle", mode, totalFound: 0 });
  shouldStop = false;
  send("scrapingComplete", {});
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "startScraping") { sendResponse({ ok: true }); shouldStop = false; runAll(msg.config || {}).catch(e => send("log", { text: "Error: " + e.message })); return true; }
  if (msg.action === "stopScraping") { sendResponse({ ok: true }); shouldStop = true; Storage.setState({ stopRequested: true }); }
  if (msg.action === "ping") { sendResponse({ ok: true }); }
});

(async function init() {
  const saved = await chrome.storage.local.get("activeScrapeConfig");
  const sc = saved.activeScrapeConfig;
  if (!sc || !sc.config) return;
  const stopReq = await Storage.getState();
  if (stopReq.stopRequested) { await chrome.storage.local.remove("activeScrapeConfig"); await Storage.setState({ stopRequested: false }); return; }
  if (window.location.href.includes("linkedin.com/jobs/search") || window.location.href.includes("linkedin.com/search/results/content")) {
    await rand(500, 1000);
    send("log", { text: "Resuming scrape session..." });
    await runAll(sc.config);
  }
})();
