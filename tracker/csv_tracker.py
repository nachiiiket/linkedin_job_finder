import csv
import os
from datetime import datetime
from pathlib import Path

COLUMNS = [
    "job_id", "date_found", "position", "company", "location",
    "poster_name", "poster_title", "poster_profile_url",
    "job_url", "email", "applied", "connection_sent", "notes",
    "full_post"
]


class CSVTracker:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._seen_job_ids: set = set()
        self._seen_poster_keys: set = set()  # "poster_name|position"
        self._init_file()
        self._load_existing()

    def _init_file(self):
        if not Path(self.filepath).exists():
            with open(self.filepath, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=COLUMNS).writeheader()

    def _load_existing(self):
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    jid = row.get("job_id", "").strip()
                    if jid:
                        self._seen_job_ids.add(jid)
                    pname = row.get("poster_name", "").strip().lower()
                    pos = row.get("position", "").strip().lower()
                    if pname and pos:
                        self._seen_poster_keys.add(f"{pname}|{pos}")
        except Exception:
            pass

    def is_duplicate(self, job_id: str = "", poster_name: str = "", position: str = "") -> bool:
        if job_id and job_id in self._seen_job_ids:
            return True
        key = f"{poster_name.strip().lower()}|{position.strip().lower()}"
        return key in self._seen_poster_keys

    def save(self, job: dict) -> bool:
        """Save job to CSV. Returns False if duplicate."""
        jid = job.get("job_id", "").strip()
        pname = job.get("poster_name", "")
        pos = job.get("position", "")

        if self.is_duplicate(job_id=jid, poster_name=pname, position=pos):
            return False

        # Fill defaults
        row = {col: job.get(col, "") for col in COLUMNS}
        if not row["date_found"]:
            row["date_found"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not row["applied"]:
            row["applied"] = "No"
        if not row["connection_sent"]:
            row["connection_sent"] = "No"

        with open(self.filepath, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COLUMNS).writerow(row)

        # Track
        if jid:
            self._seen_job_ids.add(jid)
        if pname and pos:
            self._seen_poster_keys.add(f"{pname.strip().lower()}|{pos.strip().lower()}")

        return True

    def update_field(self, job_id: str, field: str, value: str):
        """Update a specific field in existing row."""
        rows = []
        with open(self.filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("job_id") == job_id:
                    row[field] = value
                rows.append(row)
        with open(self.filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def deduplicate(self):
        """Remove duplicate rows keeping the first occurrence."""
        seen = set()
        kept = []
        removed = 0
        with open(self.filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                jid = row.get("job_id", "").strip()
                key = f"{row.get('poster_name', '').strip().lower()}|{row.get('position', '').strip().lower()}"
                dedup_key = jid or key
                if dedup_key in seen:
                    removed += 1
                    continue
                seen.add(dedup_key)
                kept.append(row)

        if removed:
            with open(self.filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(kept)
            self._load_existing()
            print(f"  CSV dedup: removed {removed} duplicate rows")

    def get_stats(self) -> dict:
        total = len(self._seen_job_ids)
        applied = 0
        connected = 0
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("applied", "").lower() == "yes":
                        applied += 1
                    if row.get("connection_sent", "").lower() == "yes":
                        connected += 1
        except Exception:
            pass
        return {"total": total, "applied": applied, "connected": connected}
