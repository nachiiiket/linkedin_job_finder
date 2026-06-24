import asyncio
import random
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

async def launch_browser(config: dict) -> tuple[Browser, BrowserContext, Page]:
    """Launch Playwright browser with anti-detection settings."""
    pw = await async_playwright().start()

    browser_cfg = config.get("browser", {})
    headless = browser_cfg.get("headless", False)
    slow_mo = browser_cfg.get("slow_mo_ms", 50)

    browser = await pw.chromium.launch(
        headless=headless,
        slow_mo=slow_mo,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--start-maximized",
        ],
    )

    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 768},
        java_script_enabled=True,
        accept_downloads=True,
        locale="en-US",
        timezone_id="Asia/Kolkata",
    )

    # Remove automation flag
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    page = await context.new_page()
    return browser, context, page


async def human_delay(config: dict):
    """Random delay to mimic human speed."""
    browser_cfg = config.get("browser", {})
    min_ms = browser_cfg.get("human_delay_min_ms", 800)
    max_ms = browser_cfg.get("human_delay_max_ms", 2500)
    delay = random.randint(min_ms, max_ms) / 1000
    await asyncio.sleep(delay)


async def human_type(page: Page, selector: str, text: str):
    """Type text char by char with random delays."""
    await page.click(selector)
    for char in text:
        await page.keyboard.type(char, delay=random.randint(40, 120))


async def scroll_page(page: Page, times: int = 3, delay: float = 1.5):
    """Scroll page to trigger lazy loading."""
    for _ in range(times):
        await page.evaluate(
            "window.scrollBy(0, Math.floor(Math.random() * 400 + 300))"
        )
        await asyncio.sleep(delay)
