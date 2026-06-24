# LinkedIn Job Bot

Automated LinkedIn job search and tracking. Searches job listings and feed posts, extracts details, and tracks everything in a CSV.

## Features

- **Job search** — scrape LinkedIn job listings by keywords/locations
- **Post search** — search LinkedIn feed posts for hiring signals, parse with regex
- **Duplicate detection** — skip already-tracked jobs across runs
- **Connection requests** — auto-send connection requests to job posters
- **Easy Apply** — auto-fill and submit Easy Apply forms (opt-in)
- **Email lookup** — find company emails via Hunter.io (opt-in)
- **Session persistence** — saves browser session to avoid repeated logins

## Prerequisites

- Python 3.10+
- A LinkedIn account
- Google Chrome or Chromium (installed by Playwright)

## Setup

1. **Clone the repo**

```bash
git clone https://github.com/nachiiiket/linkedin_job_finder.git
cd linkedin_job_finder
```

2. **Create your config**

```bash
cp config.example.json config.json
```

Then edit `config.json` with your desired search terms, locations, and filters.

3. **Create `.env` file**

```bash
notepad .env
```

Add your LinkedIn credentials:

```
LINKEDIN_EMAIL=your.email@example.com
LINKEDIN_PASSWORD=your_password
```

The `.env` file is gitignored and will never be committed.

4. **Set up virtual environment & install**

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
playwright install chromium
```

## Configuration

### `config.json`

| Section | Description |
|---|---|
| `search.job_roles` | List of job titles to search for on the Jobs page |
| `search.locations` | List of locations (empty = LinkedIn default) |
| `search.easy_apply_only` | Only show Easy Apply jobs |
| `search.posted_within_days` | How recent jobs must be |
| `search.max_jobs_per_run` | Max jobs to collect per run |
| `filters.target_poster_titles` | Only save jobs posted by people with these titles |
| `filters.exclude_companies` | Skip jobs from these companies |
| `actions.auto_easy_apply` | Enable auto-apply (requires `--apply` flag) |
| `actions.send_connection_request` | Enable connection requests (requires `--connect` flag) |
| `actions.hunter_api_key` | Hunter.io API key for email lookup |
| `llm.enabled` | Set to `true` to enable LLM-based post parsing |
| `browser.headless` | Set to `true` to run browser in headless mode |

### `.env`

| Variable | Required | Description |
|---|---|---|
| `LINKEDIN_EMAIL` | Yes | Your LinkedIn email |
| `LINKEDIN_PASSWORD` | Yes | Your LinkedIn password |

## Usage

```bash
# Search both Jobs and Posts (default)
python main.py

# Jobs only
python main.py --mode jobs

# Posts only
python main.py --mode posts

# Enable connection requests
python main.py --connect

# Enable Easy Apply
python main.py --apply

# Combine flags
python main.py --mode jobs --connect
```

Run with `--mode posts` first to collect job leads, then review them before running with `--connect`.

## Output

- **CSV** — `job_tracker.csv` with all collected job/posting details
- **XLSX** — Excel export generated automatically after each run
- **Logs** — timestamped run logs saved to `logs/` directory

## Security

- `.env`, `config.json`, and `linkedin_session.json` are gitignored and never committed
- Session files contain auth tokens — keep them secure
- Never share your `.env` or `config.json` files

## License

MIT
