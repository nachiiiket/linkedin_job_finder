import asyncio
import re
from datetime import datetime
from playwright.async_api import Page
from .browser import human_delay, scroll_page


def _build_job_search_url(keyword: str, location: str, easy_apply: bool, days: int) -> str:
    import urllib.parse
    params = {
        "keywords": keyword,
        "location": location,
        "sortBy": "DD",
    }
    if easy_apply:
        params["f_AL"] = "true"
    if days <= 1:
        params["f_TPR"] = "r86400"
    elif days <= 7:
        params["f_TPR"] = "r604800"
    elif days <= 30:
        params["f_TPR"] = "r2592000"

    query = urllib.parse.urlencode(params)
    return f"https://www.linkedin.com/jobs/search/?{query}"


async def _click_see_more_job_desc(page: Page):
    """Click 'see more' in the job description panel to reveal full text."""
    for sel in [
        "button:has-text('see more')",
        "button:has-text('Show more')",
        ".jobs-description__footer button",
        ".description__see-more-button",
        "button[data-tracking-control-name='public_jobs_show-more']",
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1000):
                await btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass


async def _extract_emails_from_text(page: Page) -> str:
    """Extract emails from job description panel."""
    return await page.evaluate("""() => {
        const desc = document.querySelector('.jobs-description-content') ||
                     document.querySelector('.jobs-box__body') ||
                     document.querySelector('.jobs-unified-top-card') ||
                     document.querySelector('main');
        const text = desc ? desc.innerText : document.body.innerText;
        const regex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/g;
        const matches = text.match(regex) || [];
        const unique = [...new Set(matches)];
        return unique.filter(e => !e.includes('.png') && !e.includes('.jpg')).join(', ');
    }""")


async def get_job_ids_on_page(page: Page) -> list[str]:
    """Get all job IDs visible in the left panel."""
    await scroll_page(page, times=4, delay=1.2)
    job_ids = await page.evaluate("""
        () => {
            const cards = document.querySelectorAll('[data-job-id]');
            return Array.from(cards).map(c => c.getAttribute('data-job-id')).filter(Boolean);
        }
    """)
    return list(set(job_ids))


async def click_job_card(page: Page, job_id: str) -> bool:
    """Click specific job card to load its details panel."""
    try:
        card = page.locator(f'[data-job-id="{job_id}"]').first
        await card.scroll_into_view_if_needed()
        await card.click()
        await asyncio.sleep(1.5)
        return True
    except Exception:
        return False


async def extract_job_details(page: Page, job_id: str) -> dict:
    """Extract all details from the job detail panel."""
    data = {
        "job_id": job_id,
        "date_found": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "position": "",
        "company": "",
        "location": "",
        "poster_name": "",
        "poster_title": "",
        "poster_profile_url": "",
        "job_url": "",
        "email": "",
        "applied": "No",
        "connection_sent": "No",
        "notes": "",
    }

    try:
        job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
        data["job_url"] = job_url

        await page.wait_for_selector(".jobs-unified-top-card", timeout=5000)

        try:
            pos_el = page.locator(
                ".jobs-unified-top-card__job-title h1, "
                ".t-24.t-bold.jobs-unified-top-card__job-title"
            ).first
            data["position"] = (await pos_el.inner_text(timeout=3000)).strip()
        except Exception:
            pass

        try:
            co_el = page.locator(
                ".jobs-unified-top-card__company-name a, "
                ".jobs-unified-top-card__company-name"
            ).first
            data["company"] = (await co_el.inner_text(timeout=3000)).strip()
        except Exception:
            pass

        try:
            loc_el = page.locator(
                ".jobs-unified-top-card__bullet, "
                ".jobs-unified-top-card__workplace-type"
            ).first
            data["location"] = (await loc_el.inner_text(timeout=3000)).strip()
        except Exception:
            pass

        await _click_see_more_job_desc(page)

        email = await _extract_emails_from_text(page)
        if email:
            data["email"] = email

        poster = await _extract_poster(page)
        data.update(poster)

    except Exception as e:
        data["notes"] = f"Extract error: {str(e)[:80]}"

    return data


async def _extract_poster(page: Page) -> dict:
    """Extract the hiring manager / recruiter info from hirer card."""
    result = {"poster_name": "", "poster_title": "", "poster_profile_url": ""}

    selectors = [
        ".hirer-card__hirer-information",
        ".jobs-poster__name",
        ".jobs-contact-section",
    ]

    for sel in selectors:
        try:
            el = page.locator(sel).first
            await el.wait_for(timeout=2000)

            try:
                name_el = el.locator("a span, .jobs-poster__name").first
                result["poster_name"] = (await name_el.inner_text(timeout=2000)).strip()
            except Exception:
                try:
                    name_el = el.locator("strong, b, h3").first
                    result["poster_name"] = (await name_el.inner_text(timeout=2000)).strip()
                except Exception:
                    pass

            try:
                title_el = el.locator(
                    ".hirer-card__hirer-job-title, .jobs-poster__subtitle, .t-14"
                ).first
                result["poster_title"] = (await title_el.inner_text(timeout=2000)).strip()
            except Exception:
                pass

            try:
                link_el = el.locator("a").first
                href = await link_el.get_attribute("href", timeout=2000)
                if href:
                    if href.startswith("/"):
                        href = f"https://www.linkedin.com{href}"
                    href = href.split("?")[0]
                    result["poster_profile_url"] = href
            except Exception:
                pass

            if result["poster_name"]:
                break

        except Exception:
            continue

    return result


async def has_easy_apply(page: Page) -> bool:
    try:
        btn = page.locator(".jobs-apply-button--top-card").first
        text = await btn.inner_text(timeout=2000)
        return "easy apply" in text.lower()
    except Exception:
        return False


async def load_next_page(page: Page, current_page: int) -> bool:
    try:
        next_btn = page.locator(
            f'button[aria-label="Page {current_page + 1}"], '
            f'li.artdeco-pagination__indicator--number:nth-child({current_page + 1}) button'
        ).first
        await next_btn.scroll_into_view_if_needed()
        await next_btn.click()
        await asyncio.sleep(3)
        return True
    except Exception:
        return False


def matches_target_poster(poster_title: str, target_titles: list[str]) -> bool:
    if not target_titles:
        return True
    title_lower = poster_title.lower()
    return any(t.lower() in title_lower for t in target_titles)
