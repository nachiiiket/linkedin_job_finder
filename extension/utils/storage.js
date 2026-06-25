const COLUMNS = [
  "job_id", "date_found", "position", "company", "location",
  "poster_name", "poster_title", "poster_profile_url",
  "job_url", "email", "applied", "connection_sent", "notes",
  "full_post"
];

const STORAGE_KEYS = {
  JOBS: "jobs",
  PREFS: "preferences",
  STATE: "scrapingState",
};

const defaultPreferences = {
  jobRoles: [
    "AI Engineer", "ML Engineer", "Machine Learning Engineer",
    "Artificial Intelligence Engineer", "AI/ML Engineer",
    "Gen AI Engineer", "Generative AI Engineer",
    "AI Researcher", "Deep Learning Engineer", "NLP Engineer",
    "Computer Vision Engineer", "Prompt Engineer", "LLM Engineer",
    "MLOps Engineer", "Data Scientist", "Applied Scientist", "AI Architect"
  ],
  locations: ["Pune", "Bangalore", "Hyderabad"],
  excludeCompanies: [],
  easyApplyOnly: true,
  postedWithinDays: 1,
  maxJobsPerRun: 50,
  excludedKeywords: ["senior only", "10+ years"],
  targetPosterTitles: [
    "Talent Acquisition", "Recruiter", "HR", "Hiring Manager",
    "Technical Recruiter", "People Operations", "Talent Partner",
    "Head of Talent", "VP of Engineering", "CTO", "Engineering Manager",
    "Team Lead", "Tech Lead", "Senior Engineer", "Staff Engineer",
    "Founder", "Co-Founder", "CEO", "Director of Engineering"
  ]
};

const Storage = {
  async getJobs() {
    const result = await chrome.storage.local.get(STORAGE_KEYS.JOBS);
    return result.jobs || [];
  },

  async saveJob(job) {
    const jobs = await this.getJobs();
    const jid = (job.job_id || "").trim();
    const pname = (job.poster_name || "").trim().toLowerCase();
    const pos = (job.position || "").trim().toLowerCase();

    const isDup = jobs.some(j => {
      if (jid && j.job_id === jid) return true;
      return j.poster_name?.toLowerCase() === pname && j.position?.toLowerCase() === pos;
    });
    if (isDup) return false;

    const row = {};
    COLUMNS.forEach(col => { row[col] = job[col] || ""; });
    if (!row.date_found) row.date_found = new Date().toLocaleString("en-IN", { timeZone: "Asia/Kolkata" });
    if (!row.applied) row.applied = "No";
    if (!row.connection_sent) row.connection_sent = "No";

    jobs.push(row);
    await chrome.storage.local.set({ jobs });
    return true;
  },

  async bulkSave(jobs) {
    const existing = await this.getJobs();
    const seen = new Map();
    existing.forEach(j => {
      if (j.job_id) seen.set(j.job_id, true);
      seen.set(`${j.poster_name?.toLowerCase()}|${j.position?.toLowerCase()}`, true);
    });

    const added = [];
    for (const job of jobs) {
      const key1 = job.job_id;
      const key2 = `${(job.poster_name || "").toLowerCase()}|${(job.position || "").toLowerCase()}`;
      if (key1 && seen.has(key1)) continue;
      if (seen.has(key2)) continue;
      if (key1) seen.set(key1, true);
      seen.set(key2, true);

      const row = {};
      COLUMNS.forEach(col => { row[col] = job[col] || ""; });
      if (!row.date_found) row.date_found = new Date().toLocaleString();
      if (!row.applied) row.applied = "No";
      if (!row.connection_sent) row.connection_sent = "No";
      added.push(row);
    }

    await chrome.storage.local.set({ jobs: [...existing, ...added] });
    return added.length;
  },

  async updateJob(jobId, updates) {
    const jobs = await this.getJobs();
    const idx = jobs.findIndex(j => j.job_id === jobId);
    if (idx === -1) return false;
    Object.assign(jobs[idx], updates);
    await chrome.storage.local.set({ jobs });
    return true;
  },

  async deduplicate() {
    const jobs = await this.getJobs();
    const seen = new Set();
    const kept = [];
    let removed = 0;
    for (const job of jobs) {
      const key = job.job_id || `${job.poster_name}|${job.position}`;
      if (seen.has(key)) { removed++; continue; }
      seen.add(key);
      kept.push(job);
    }
    if (removed > 0) {
      await chrome.storage.local.set({ jobs: kept });
    }
    return removed;
  },

  async getStats() {
    const jobs = await this.getJobs();
    return {
      total: jobs.length,
      applied: jobs.filter(j => j.applied?.toLowerCase() === "yes").length,
      connected: jobs.filter(j => j.connection_sent?.toLowerCase() === "yes").length,
    };
  },

  async getPreferences() {
    const result = await chrome.storage.sync.get(STORAGE_KEYS.PREFS);
    return result.preferences || defaultPreferences;
  },

  async savePreferences(prefs) {
    await chrome.storage.sync.set({ preferences: prefs });
  },

  async getState() {
    const result = await chrome.storage.session.get(STORAGE_KEYS.STATE);
    return result.scrapingState || { status: "idle", currentQueryIndex: 0, currentPage: 1, totalFound: 0 };
  },

  async setState(state) {
    await chrome.storage.session.set({ scrapingState: state });
  }
};
