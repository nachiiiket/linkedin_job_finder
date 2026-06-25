const SCRAPING_CONFIG_KEY = "activeScrapeConfig";

let scrapingActive = false;
let shouldStop = false;

function postMessage(action, data) {
  try { chrome.runtime.sendMessage({ action, ...(data || {}) }); } catch(e) {}
}

function randomDelay(min, max) {
  return new Promise(r => setTimeout(r, min + Math.random() * (max - min)));
}

function scrollContainer() {
  const c = document.querySelector(".jobs-search-results-list, .scaffold-layout__list");
  if (c) { c.scrollTop = c.scrollHeight; }
  else { window.scrollBy(0, 400); }
}

function getJobIds() {
  const cards = document.querySelectorAll("[data-job-id]");
  return [...new Set(Array.from(cards).map(c => c.getAttribute("data-job-id")).filter(Boolean))];
}

async function clickJobCard(jobId) {
  const card = document.querySelector(`[data-job-id="${jobId}"]`);
  if (!card) return false;
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  await randomDelay(300, 700);
  card.click();
  await randomDelay(500, 1000);
  return true;
}

function extractJobDetails(jobId) {
  const data = {
    job_id: jobId,
    date_found: new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }),
    position: "", company: "", location: "",
    poster_name: "", poster_title: "", poster_profile_url: "",
    job_url: `https://www.linkedin.com/jobs/view/${jobId}/`,
    email: "", applied: "No", connection_sent: "No", notes: "", full_post: ""
  };

  try {
    const el = document.querySelector(
      ".jobs-unified-top-card__job-title h1, " +
      ".t-24.t-bold.jobs-unified-top-card__job-title, " +
      ".jobs-details-top-card__job-title"
    );
    if (el) data.position = el.innerText.trim();
  } catch(e) {}

  try {
    const el = document.querySelector(
      ".jobs-unified-top-card__company-name a, " +
      ".jobs-unified-top-card__company-name, " +
      ".jobs-details-top-card__company-info a"
    );
    if (el) data.company = el.innerText.trim();
  } catch(e) {}

  try {
    const el = document.querySelector(
      ".jobs-unified-top-card__bullet, " +
      ".jobs-details-top-card__bullet, " +
      ".jobs-unified-top-card__workplace-type"
    );
    if (el) data.location = el.innerText.trim();
  } catch(e) {}

  try {
    const btn = document.querySelector(
      "button:has-text('see more'), button:has-text('Show more'), " +
      ".jobs-description__footer button, .description__see-more-button"
    );
    if (btn && btn.offsetParent !== null) btn.click();
  } catch(e) {}

  try {
    const desc = document.querySelector(
      ".jobs-description-content, .jobs-box__body, main"
    );
    if (desc) {
      const text = desc.innerText || "";
      const emails = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g) || [];
      data.email = [...new Set(emails)].filter(e => !e.includes(".png") && !e.includes(".jpg")).join(", ");
      data.full_post = text.slice(0, 2000);
    }
  } catch(e) {}

  const poster = extractPosterInfo();
  Object.assign(data, poster);
  return data;
}

function extractPosterInfo() {
  const result = { poster_name: "", poster_title: "", poster_profile_url: "" };
  for (const sel of [
    ".hirer-card__hirer-information", ".jobs-poster__name", ".jobs-contact-section"
  ]) {
    const el = document.querySelector(sel);
    if (!el) continue;
    try {
      const n = el.querySelector("a span, .jobs-poster__name, strong, b, h3");
      if (n) result.poster_name = n.innerText.trim();
    } catch(e) {}
    try {
      const t = el.querySelector(".hirer-card__hirer-job-title, .jobs-poster__subtitle, .t-14");
      if (t) result.poster_title = t.innerText.trim();
    } catch(e) {}
    try {
      const a = el.querySelector("a");
      if (a) {
        let href = a.getAttribute("href") || "";
        if (href.startsWith("/")) href = "https://www.linkedin.com" + href;
        result.poster_profile_url = href.split("?")[0];
      }
    } catch(e) {}
    if (result.poster_name) break;
  }
  return result;
}

async function goToNextPage(currentPage) {
  for (const sel of [
    `button[aria-label="Page ${currentPage + 1}"]`,
    `li.artdeco-pagination__indicator--number:nth-child(${currentPage + 1}) button`,
    "button.artdeco-pagination__button--next:not([disabled])",
    "button.jobs-search-pagination__next-button:not([disabled])"
  ]) {
    try {
      const btn = document.querySelector(sel);
      if (btn && !btn.disabled) {
        btn.scrollIntoView({ block: "center" });
        await randomDelay(300, 600);
        btn.click();
        await new Promise(r => setTimeout(r, 2500));
        const newCards = await waitForElement("[data-job-id]", 5000);
        return !!newCards;
      }
    } catch(e) {}
  }
  return false;
}

function waitForElement(selector, timeout) {
  return new Promise(resolve => {
    const el = document.querySelector(selector);
    if (el) return resolve(el);
    const obs = new MutationObserver(() => {
      const found = document.querySelector(selector);
      if (found) { obs.disconnect(); resolve(found); }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => { obs.disconnect(); resolve(null); }, timeout);
  });
}

function matchesPoster(title, targets) {
  if (!targets || !targets.length) return true;
  const lower = (title || "").toLowerCase();
  return targets.some(t => lower.includes(t.toLowerCase()));
}

function buildSearchUrl(keyword, location, config) {
  const p = new URLSearchParams();
  p.set("keywords", keyword);
  if (location) p.set("location", location);
  p.set("sortBy", "DD");
  if (config.easyApplyOnly) p.set("f_AL", "true");
  const days = config.postedWithinDays || 1;
  if (days <= 1) p.set("f_TPR", "r86400");
  else if (days <= 7) p.set("f_TPR", "r604800");
  else if (days <= 30) p.set("f_TPR", "r2592000");
  return `https://www.linkedin.com/jobs/search/?${p.toString()}`;
}

async function scrapeCurrentPage(config) {
  const maxJobs = config.maxJobsPerRun || 50;
  const stats = await chrome.storage.local.get("scrapeStats");
  let total = stats.scrapeStats?.totalFound || 0;
  let pageNum = stats.scrapeStats?.currentPage || 1;
  const loaded = total;

  await waitForElement("[data-job-id], .jobs-search-results-list", 10000);
  await randomDelay(1500, 2500);

  while (total < maxJobs && !shouldStop) {
    scrollContainer();
    await randomDelay(600, 1000);

    const jobIds = getJobIds();
    if (!jobIds.length) break;

    postMessage("log", { text: `Page ${pageNum}: ${jobIds.length} cards` });

    for (const jid of jobIds) {
      if (shouldStop || total >= maxJobs) break;

      const existing = await chrome.storage.local.get("jobs");
      const jobs = existing.jobs || [];
      if (jobs.some(j => j.job_id === jid)) {
        postMessage("log", { text: `Skipping duplicate: ${jid}` });
        continue;
      }

      if (!(await clickJobCard(jid))) {
        postMessage("log", { text: `Could not click: ${jid}` });
        continue;
      }

      const details = extractJobDetails(jid);

      if (!matchesPoster(details.poster_title, config.targetPosterTitles)) {
        postMessage("log", { text: `Skipping - poster: ${details.poster_title || "?"}` });
        continue;
      }

      if (config.excludeCompanies && config.excludeCompanies.length) {
        const co = (details.company || "").toLowerCase();
        if (config.excludeCompanies.some(e => co.includes(e.toLowerCase()))) continue;
      }

      const saved = await Storage.saveJob(details);
      if (saved) {
        total++;
        postMessage("jobFound", { job: details });
        postMessage("log", { text: `[${total}] ${details.position} @ ${details.company}` });
      }
      await randomDelay(800, 2000);
    }

    if (shouldStop || total >= maxJobs) break;

    const hasNext = await goToNextPage(pageNum);
    if (!hasNext) break;
    pageNum++;
    await chrome.storage.local.set({
      scrapeStats: { totalFound: total, currentPage: pageNum }
    });
    await randomDelay(1000, 2000);
  }

  return total - loaded;
}

async function runAllQueries(config) {
  scrapingActive = true;
  shouldStop = false;

  const queries = [];
  for (const role of config.jobRoles) {
    if (config.locations && config.locations.length) {
      for (const loc of config.locations) {
        queries.push({ keyword: role, location: loc, label: `${role} @ ${loc}` });
      }
    } else {
      queries.push({ keyword: role, location: "", label: role });
    }
  }

  const savedState = await chrome.storage.session.get(SCRAPING_CONFIG_KEY);
  const state = savedState[SCRAPING_CONFIG_KEY];
  let startIdx = state?.currentQueryIndex || 0;

  if (startIdx === 0 && !state?.pageDone) {
    await chrome.storage.local.set({
      scrapeStats: { totalFound: 0, currentPage: 1 }
    });
  }

  for (let i = startIdx; i < queries.length && !shouldStop; i++) {
    const q = queries[i];
    const url = buildSearchUrl(q.keyword, q.location, config);

    await chrome.storage.session.set({
      [SCRAPING_CONFIG_KEY]: {
        config,
        queries,
        currentQueryIndex: i,
        currentPage: 1,
        pageDone: i < startIdx,
        url
      }
    });

    postMessage("log", { text: `=== ${q.label} ===` });

    if (window.location.href !== url) {
      window.location.href = url;
      return;
    }

    await scrapeCurrentPage(config);
  }

  scrapingActive = false;
  await chrome.storage.session.remove(SCRAPING_CONFIG_KEY);
  await chrome.storage.local.remove("scrapeStats");
  postMessage("scrapingComplete", {});
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "startScraping") {
    runAllQueries(msg.config || {}).catch(console.error);
    sendResponse({ ok: true });
    return true;
  }
  if (msg.action === "stopScraping") {
    shouldStop = true;
    scrapingActive = false;
    sendResponse({ ok: true });
  }
  if (msg.action === "ping") {
    sendResponse({ ok: true, active: scrapingActive });
  }
});

(async () => {
  const saved = await chrome.storage.session.get(SCRAPING_CONFIG_KEY);
  const state = saved[SCRAPING_CONFIG_KEY];
  if (state && state.config && state.url) {
    if (window.location.href.includes("linkedin.com/jobs/search")) {
      await randomDelay(500, 1000);
      postMessage("log", { text: "Resuming scrape session..." });
      await runAllQueries(state.config);
    }
  }
})();
