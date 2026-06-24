import asyncio
import os
import urllib.parse
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page
from .browser import scroll_page

# --- regex helpers ---

_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
_PHONE_RE = re.compile(r'[\+]?[0-9]{1,3}[-.\s]?[(\s]?[0-9]{3,5}[)\s]?[-.\s]?[0-9]{4,6}')
_YEARS_RE = re.compile(r'(\d+)\+?\s*(?:–|-|to)\s*(\d+)\s*(?:years?|yrs?)|(\d+)\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:exp|experience)', re.I)
_LOC_RE   = re.compile(r'(?:Location|Based in|Office|Hybrid|Remote|WFO|WFH)[:\s]+([A-Za-z ,]+?)(?:\n|$|\.)', re.I)

_BAD_EMAIL_PARTS = ('.png', '.jpg', '.svg', '.gif', 'example.com', 'sentry.io', 'linkedin.com')


def _clean_emails(emails: list[str]) -> list[str]:
    return [e for e in emails if not any(b in e.lower() for b in _BAD_EMAIL_PARTS)]


def _regex_extract(text: str) -> dict:
    """Fast structural extraction — supplements LLM."""
    emails  = _clean_emails(_EMAIL_RE.findall(text))
    phones  = list(set(_PHONE_RE.findall(text)))[:3]
    yr_hits = _YEARS_RE.findall(text)
    years   = None
    for g1, g2, g3 in yr_hits:
        if g3:
            years = int(g3)
            break
        if g1:
            years = int(g1)
            break
    loc_hits = _LOC_RE.findall(text)
    location = loc_hits[0].strip() if loc_hits else ""
    return {"emails": emails, "phones": phones, "min_years_exp": years, "location_hint": location}


# --- per-post see-more click ---

_SEE_MORE_JS = """(el) => {
    const btns = el.querySelectorAll('button, span[role="button"]');
    let clicked = 0;
    for (const btn of btns) {
        const t = (btn.textContent || '').trim().toLowerCase();
        if (t === 'see more' || t === '…more' || t === '...more' || t === 'show more') {
            btn.click();
            clicked++;
        }
    }
    return clicked;
}"""

_EXTRACT_META_JS = """(el) => {
    const result = { profileUrl: '', dateText: '' };
    const links = el.querySelectorAll('a[href*="/in/"]');
    for (const a of links) {
        const h = a.href || '';
        if (h.includes('/in/') && !h.includes('/feed/')) {
            result.profileUrl = h.split('?')[0];
            break;
        }
    }
    const timeEl = el.querySelector('time');
    if (timeEl) {
        result.dateText = (timeEl.getAttribute('datetime') || timeEl.textContent || '').trim();
    }
    if (!result.dateText) {
        const sp = el.querySelector('.feed-shared-actor__sub-description');
        if (sp) result.dateText = sp.textContent.trim();
    }
    return result;
}"""


async def _expand_post(element) -> None:
    """Click see-more button inside a single post element."""
    try:
        # JS click (fastest, works even if element barely visible)
        await element.evaluate(_SEE_MORE_JS)
        await asyncio.sleep(0.15)
    except Exception:
        pass

    # Playwright fallback for stubborn buttons
    for sel in [
        ".feed-shared-inline-show-more-text__button",
        "button[aria-label*='see more' i]",
        "button[aria-label*='show more' i]",
    ]:
        try:
            btn = await element.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await asyncio.sleep(0.15)
        except Exception:
            pass


# --- post container selectors ---

_POST_SELECTORS = [
    ".feed-shared-update-v2",
    "[data-urn*='activity']",
    "li.reusable-search__result-container",
    ".search-content__result",
]


async def _get_post_elements(page: Page) -> list:
    """Return all post container elements from page."""
    for sel in _POST_SELECTORS:
        els = await page.query_selector_all(sel)
        if len(els) >= 2:
            return els
    # fallback: listitem with substantial text
    all_li = await page.query_selector_all('[role="listitem"]')
    return [el for el in all_li] if all_li else []


# --- per-post text extraction ---

async def _extract_posts(page: Page) -> list[dict]:
    """
    Returns list of {index, raw_text, emails, phones, min_years_exp, location_hint, profile_url, date_text}.
    Each post has see-more expanded before text grab.
    """
    elements = await _get_post_elements(page)
    print(f"  Found {len(elements)} post elements")

    posts = []
    for i, el in enumerate(elements):
        try:
            await el.scroll_into_view_if_needed()
        except Exception:
            pass

        await _expand_post(el)

        try:
            text = (await el.inner_text()).strip()
        except Exception:
            continue

        if len(text) < 80:
            continue

        meta = await el.evaluate(_EXTRACT_META_JS)

        extracted = _regex_extract(text)
        posts.append({
            "index": i + 1,
            "raw_text": _compress_text(text),
            "profile_url": meta.get("profileUrl", ""),
            "date_text": meta.get("dateText", ""),
            **extracted,
        })

    return posts


# --- markdown builder ---

def _posts_to_markdown(posts: list[dict], query: str) -> str:
    """Convert per-post dicts to delimited markdown for LLM."""
    lines = [
        f"# Search: {query}",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Posts found:** {len(posts)}",
        "",
    ]
    for p in posts:
        lines.append(f"===POST_START:{p['index']}===")
        if p["emails"]:
            lines.append(f"[EMAILS: {', '.join(p['emails'])}]")
        if p["phones"]:
            lines.append(f"[PHONES: {', '.join(p['phones'][:2])}]")
        if p["min_years_exp"] is not None:
            lines.append(f"[MIN_EXP: {p['min_years_exp']} yrs]")
        if p["location_hint"]:
            lines.append(f"[LOCATION_HINT: {p['location_hint']}]")
        if p.get("profile_url"):
            lines.append(f"[PROFILE_URL: {p['profile_url']}]")
        if p.get("date_text"):
            lines.append(f"[DATE_TEXT: {p['date_text']}]")
        lines.append(p["raw_text"])
        lines.append(f"===POST_END:{p['index']}===")
        lines.append("")
    return "\n".join(lines)


# --- URL builder ---

def _build_search_url(query: str, sort_by: str = "date_posted") -> str:
    encoded     = urllib.parse.quote(query)
    sort_enc    = urllib.parse.quote(sort_by)
    return (
        f"https://www.linkedin.com/search/results/content/"
        f"?keywords={encoded}&origin=GLOBAL_SEARCH_HEADER"
        f"&sortBy=%22{sort_enc}%22&f_TPR=r86400"
    )


# --- public API ---

async def get_page_markdown(page: Page, query: str, sort_by: str = "date_posted") -> str:
    """Navigate, expand all posts, return per-post delimited markdown."""
    url = _build_search_url(query, sort_by)
    print(f"  >> Searching: {query}")

    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    # scroll to trigger lazy-load
    await scroll_page(page, times=5, delay=0.8)
    await asyncio.sleep(0.5)

    # page-level see-more pass first (catches some)
    await _page_level_see_more(page)

    # per-post extraction (main fix)
    posts = await _extract_posts(page)

    if not posts:
        # fallback: old whole-page text method
        print("  >> No per-post elements found, falling back to page text")
        text = await page.evaluate("document.body.innerText")
        return _compress_text(text)

    return _posts_to_markdown(posts, query)


async def _page_level_see_more(page: Page):
    """Best-effort page-wide click before per-post pass."""
    await page.evaluate("""() => {
        document.querySelectorAll('button, span[role="button"]').forEach(btn => {
            const t = (btn.textContent || '').trim().toLowerCase();
            if (t === 'see more' || t === '…more' || t === '...more') btn.click();
        });
    }""")
    await asyncio.sleep(0.3)


def save_markdown_to_file(markdown: str, label: str) -> str | None:
    out_dir = Path("search_results")
    out_dir.mkdir(exist_ok=True)

    content_chars = len(markdown.strip())
    if content_chars < 500:
        print(f"  >> Skipped ({content_chars} chars, too small)")
        return None

    safe_label = re.sub(r"[^a-zA-Z0-9_-]", "_", label)[:40]
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"search_{safe_label}_{ts}.md"
    path.write_text(markdown, encoding="utf-8")
    print(f"  >> Saved ({content_chars} chars) -> {path.name}")
    return str(path)


def _compress_text(text: str) -> str:
    text = re.sub(r'#[^\s#]+', '', text)
    text = re.sub(r'[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]', '', text)
    text = re.sub(r'https?://\S+', '<url>', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'^\s*[\*\-]\s*$', '', text, flags=re.MULTILINE)
    return text.strip()


def _fill_template(template: str, **kwargs) -> str:
    """Replace {placeholders} in template, remove unfilled ones, collapse whitespace."""
    for k, v in kwargs.items():
        template = template.replace("{" + k + "}", v)
    template = re.sub(r'\{[^}]+\}', '', template)
    template = re.sub(r'\s{2,}', ' ', template).strip()
    template = re.sub(r'\s+(AND|OR)\s*$', '', template, flags=re.I)
    template = re.sub(r'^(\s*(AND|OR)\s+)+', '', template, flags=re.I)
    return template


def _env_bool(key: str, default: bool = True) -> bool:
    val = os.environ.get(key, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def generate_search_variants(config: dict) -> list[dict]:
    job_roles = config.get("search", {}).get("job_roles", [])
    variants  = []

    location_search = _env_bool("LOCATION_SEARCH", True)
    company_search  = _env_bool("COMPANY_SEARCH", True)

    query_types = config.get("post_search", {}).get("query_types", [])

    if not query_types:
        # legacy fallback
        for role in job_roles:
            clean = role.strip()
            if not clean:
                continue
            variants.append({
                "query":   f'"Hiring" AND "{clean}"',
                "sort_by": "date_posted",
                "label":   clean.lower().replace(" ", "_")[:30],
            })
        print(f"  Generated {len(variants)} role searches")
        return variants

    for qt in query_types:
        if not qt.get("enabled", True):
            continue

        template   = qt.get("template", "")
        label_fmt  = qt.get("label_format", "{role}")
        sort_by    = qt.get("sort_by", "date_posted")
        locations  = qt.get("locations") or []
        companies  = qt.get("companies") or []

        for role in job_roles:
            clean = role.strip()
            if not clean:
                continue

            if "locations" in qt:
                if location_search:
                    for loc in locations:
                        loc_clean = loc.strip()
                        if not loc_clean:
                            continue
                        query = _fill_template(template, role=clean, location=loc_clean, company="")
                        label = _fill_template(label_fmt, role=clean.lower().replace(" ", "_"), location=loc_clean.lower().replace(" ", "_"), company="")
                        variants.append({"query": query, "sort_by": sort_by, "label": label[:50]})
                continue

            if "companies" in qt:
                if company_search:
                    for company in companies:
                        co_clean = company.strip()
                        if not co_clean:
                            continue
                        query = _fill_template(template, role=clean, location="", company=co_clean)
                        label = _fill_template(label_fmt, role=clean.lower().replace(" ", "_"), location="", company=co_clean.lower().replace(" ", "_"))
                        variants.append({"query": query, "sort_by": sort_by, "label": label[:50]})
                continue

            # plain type — no locations or companies declared
            query = _fill_template(template, role=clean, location="", company="")
            label = _fill_template(label_fmt, role=clean.lower().replace(" ", "_"), location="", company="")
            variants.append({"query": query, "sort_by": sort_by, "label": label[:50]})

    print(f"  Generated {len(variants)} role searches")
    return variants