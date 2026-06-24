import re
from datetime import datetime
from pathlib import Path

_EMAIL_TAG    = re.compile(r'\[EMAILS:\s*([^\]]+)\]')
_PHONE_TAG    = re.compile(r'\[PHONES:\s*([^\]]+)\]')
_EXP_TAG      = re.compile(r'\[MIN_EXP:\s*(\d+)[^\]]*\]')
_LOC_TAG      = re.compile(r'\[LOCATION_HINT:\s*([^\]]+)\]')
_URL_TAG      = re.compile(r'\[PROFILE_URL:\s*([^\]]+)\]')
_DATE_TAG     = re.compile(r'\[DATE_TEXT:\s*([^\]]+)\]')

_POST_BLOCK   = re.compile(
    r'===POST_START:(\d+)===(.*?)===POST_END:\1===',
    re.DOTALL
)

_WORD         = re.compile(r'\w+')
_TITLE_AT     = re.compile(r'(.+?)\s+(?:at|@)\s+(.+)', re.I)
_ROLE_IN_BODY = re.compile(r'(?:hiring|looking\s+for|we\s+are\s+hiring|we\'re\s+hiring)\s*:?\s*(.+?)(?:\n|$)', re.I)
_CO_IN_BODY   = re.compile(r'(?:Company\s*:\s*)(.+?)(?:\n|$)', re.I)
_LOC_IN_BODY  = re.compile(r'(?:Location\s*:\s*|Office\s*:\s*|Based\s+in\s+)(.+?)(?:\n|$)', re.I)
_EXP_IN_BODY  = re.compile(r'(\d+)\+?\s*(?:to|–|-)\s*(\d+)\s*(?:years?|yrs?)', re.I)
_SKILL_WORDS  = {
    "python","java","c++","javascript","typescript","rust","go","sql","nosql",
    "pytorch","tensorflow","keras","jax","transformers","langchain","llama",
    "docker","kubernetes","k8s","aws","gcp","azure","mlops","ci/cd","git",
    "machine learning","deep learning","nlp","computer vision","reinforcement learning",
    "ai","generative ai","llm","rag","agent","fine-tuning","spark","hadoop",
    "flask","fastapi","django","react","angular","node.js","redis","postgresql",
    "mongodb","kafka","airflow","terraform","ansible","prometheus","grafana",
}


def _extract_tags(block: str) -> dict:
    em = _EMAIL_TAG.search(block)
    ph = _PHONE_TAG.search(block)
    ex = _EXP_TAG.search(block)
    lo = _LOC_TAG.search(block)
    ur = _URL_TAG.search(block)
    dt = _DATE_TAG.search(block)
    return {
        "email":         em.group(1).split(",")[0].strip() if em else "",
        "phones":        ph.group(1).strip() if ph else "",
        "min_years_exp": int(ex.group(1)) if ex else None,
        "location_hint": lo.group(1).strip() if lo else "",
        "profile_url":   ur.group(1).strip() if ur else "",
        "date_text":     dt.group(1).strip() if dt else "",
    }


def _looks_like_name(line: str) -> bool:
    words = line.strip().split()
    if len(words) < 2 or len(words) > 5:
        return False
    if not all(w[0].isupper() for w in words if w):
        return False
    bad = {"follow", "following", "like", "comment", "share", "send", "…more", "...more", "show more", "see more", "repost", "reply", "message"}
    if line.strip().lower() in bad:
        return False
    return True


def _looks_like_title(line: str) -> bool:
    title_keywords = {"engineer", "scientist", "manager", "director", "head", "lead", "architect", "specialist", "analyst", "consultant", "developer", "researcher", "intern", "fellow", "officer", "vp", "vice president", "president", "ceo", "cto", "coo", "founder", "co-founder"}
    lower = line.lower()
    for kw in title_keywords:
        if kw in lower:
            return True
    if "@" in line or " at " in lower:
        return True
    return False


def _extract_skills(text: str, max_count: int = 8) -> list[str]:
    found = set()
    lower = text.lower()
    for skill in _SKILL_WORDS:
        if skill in lower:
            found.add(skill)
            if len(found) >= max_count:
                break
    return sorted(found, key=lambda s: lower.index(s))[:max_count]


def _heuristic_parse(block: str, tags: dict, query_role: str = "") -> dict:
    lines = [l.strip() for l in block.split("\n") if l.strip()]
    if not lines:
        return {}

    poster_name = ""
    poster_title = ""
    company = tags.get("profile_url") and _company_from_url(tags["profile_url"]) or ""
    location = tags.get("location_hint", "")
    position = query_role
    snippet = ""
    skills = []
    min_years = tags.get("min_years_exp")

    for line in lines:
        if not poster_name and _looks_like_name(line):
            poster_name = line
            continue
        if poster_name and not poster_title and _looks_like_title(line):
            poster_title = line
            m = _TITLE_AT.search(line)
            if m and not company:
                company = m.group(2).strip()
            continue

    body_start = 0
    for i, line in enumerate(lines):
        if not _looks_like_name(line) and not _looks_like_title(line) and "•" not in line and "following" not in line.lower():
            body_start = i
            break
    body = "\n".join(lines[body_start:])

    m = _ROLE_IN_BODY.search(body)
    if m:
        position = m.group(1).strip().rstrip(".!,")
        for prefix in ("for a ", "for an ", "for ", "a ", "an ", "the "):
            if position.lower().startswith(prefix):
                position = position[len(prefix):]
                break

    m = _CO_IN_BODY.search(body)
    if m:
        company = m.group(1).strip().rstrip(":")

    m = _LOC_IN_BODY.search(body)
    if m:
        location = m.group(1).strip().rstrip("]")
    elif tags.get("location_hint"):
        location = tags["location_hint"]

    snippet = body[:300].strip()

    skills = _extract_skills(body)

    if min_years is None:
        m = _EXP_IN_BODY.search(body)
        if m:
            min_years = int(m.group(1))

    email = tags.get("email", "")

    raw_id = f"{poster_name}{company}{position}".lower()
    job_id = re.sub(r"[^a-z0-9]", "", raw_id)[-25:] if raw_id else ""

    return {
        "job_id":            job_id or "",
        "date_found":        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "position":          position[:200],
        "company":           company[:100],
        "location":          location[:100],
        "poster_name":       poster_name[:80],
        "poster_title":      poster_title[:100],
        "poster_profile_url": tags.get("profile_url", "")[:200],
        "job_url":           "",
        "email":             email[:100],
        "applied":           "No",
        "connection_sent":   "No",
        "notes":             f"from_regex|date:{tags.get('date_text','')[:20]}|skills:{', '.join(skills[:5])[:80]}" if skills else f"from_regex|date:{tags.get('date_text','')[:20]}",
        "full_post":         body,
    }


def _company_from_url(url: str) -> str:
    m = re.search(r'/in/([^/?#]+)', url)
    if m:
        name = m.group(1).replace("-", " ").replace("_", " ")
        return name.title()
    return ""


def parse_page_markdown(markdown: str, config: dict = None) -> list[dict]:
    if not markdown.strip():
        return []

    query_role = ""
    fm = markdown.split("\n")[0]
    if fm.startswith("# Search:"):
        q = fm.replace("# Search:", "").strip()
        m = re.search(r'"([^"]+)"', q)
        if m:
            query_role = m.group(1)

    blocks = _POST_BLOCK.findall(markdown)
    if not blocks:
        return []

    results = []
    for idx, block_text in blocks:
        block_text = block_text.strip()
        if not block_text:
            continue
        tags = _extract_tags(block_text)
        row = _heuristic_parse(block_text, tags, query_role)
        if row.get("poster_name") or row.get("email"):
            results.append(row)

    return results


def parse_md_file(md_path: str, config: dict = None) -> list[dict]:
    content = Path(md_path).read_text(encoding="utf-8")
    return parse_page_markdown(content, config)
