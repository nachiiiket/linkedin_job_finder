import asyncio
import json
from pathlib import Path
from playwright.async_api import Page
from .browser import human_type, human_delay

SESSION_FILE = Path("linkedin_session.json")


async def _save_session(context):
    """Save browser context cookies + localStorage to file."""
    try:
        cookies = await context.cookies()
        state = await context.storage_state()
        session_data = {
            "cookies": cookies,
            "origins": state.get("origins", []),
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
        SESSION_FILE.write_text(json.dumps(session_data, indent=2), encoding="utf-8")
        print(f"  >> Session saved ({len(cookies)} cookies)")
        return True
    except Exception as e:
        print(f"  !! Failed to save session: {e}")
        return False


async def _load_session(context):
    """Load saved session (cookies + storage). Returns True if session was restored."""
    if not SESSION_FILE.exists():
        return False
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        if data.get("cookies"):
            await context.add_cookies(data["cookies"])
        if data.get("origins"):
            await context.add_init_script(
                f"localStorage.setItem('session_restored', 'true');"
            )
        print(f"  >> Session restored ({len(data.get('cookies', []))} cookies)")
        return True
    except Exception as e:
        print(f"  !! Failed to load session: {e}")
        return False


async def _find_login_fields(page: Page):
    """Detect login field selectors on the page."""
    try:
        email_input = page.get_by_role("textbox", name="Email or phone")
        pass_input = page.get_by_role("textbox", name="Password")
        if await email_input.is_visible(timeout=2000) and await pass_input.is_visible(timeout=2000):
            return email_input, pass_input
    except Exception:
        pass

    try:
        email_input = page.get_by_label("Email or phone").nth(1)
        pass_input = page.get_by_label("Password").nth(1)
        if await email_input.is_visible(timeout=2000) and await pass_input.is_visible(timeout=2000):
            return email_input, pass_input
    except Exception:
        pass

    try:
        email_input = page.locator("input[type='email']").nth(1)
        pass_input = page.locator("input[type='password']").nth(1)
        if await email_input.is_visible(timeout=2000) and await pass_input.is_visible(timeout=2000):
            return email_input, pass_input
    except Exception:
        pass

    return None


async def login(page: Page, context, config: dict) -> bool:
    """Log in to LinkedIn with session persistence. Returns True on success."""
    creds = config.get("credentials", {})
    email = creds.get("email", "")
    password = creds.get("password", "")

    if not email or not password:
        raise ValueError("Missing credentials in config.json")

    # Try to restore session first
    session_restored = await _load_session(context)
    if session_restored:
        print(">> Checking saved session...")
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)
        if "feed" in page.url or "mynetwork" in page.url:
            print("OK Session valid - already logged in")
            return True
        else:
            print("  Session expired, logging in fresh")

    print(">> Navigating to LinkedIn login...")
    await page.goto("https://www.linkedin.com/login", wait_until="load")
    await asyncio.sleep(3)

    if "feed" in page.url:
        print("OK Already logged in")
        await _save_session(context)
        return True

    print(">> Entering credentials...")
    fields = await _find_login_fields(page)
    if fields is None:
        print("XX Could not find login fields on page")
        print(f"  URL: {page.url}")
        print(f"  Title: {await page.title()}")
        body_text = await page.inner_text("body")
        print(f"  Body (first 500 chars): {body_text[:500]}")
        return False

    user_input, pass_input = fields
    await user_input.click()
    await user_input.fill(email)
    await human_delay(config)
    await pass_input.click()
    await pass_input.fill(password)
    await human_delay(config)

    await page.get_by_role("button", name="Sign in", exact=True).click()

    try:
        await page.wait_for_url("**/feed/**", timeout=20000)
        print("OK Login successful")
        await _save_session(context)
        return True
    except Exception:
        current = page.url
        if "checkpoint" in current or "challenge" in current:
            print("!! 2FA/CAPTCHA detected. Complete it manually in the browser window.")
            print("  Waiting up to 60 seconds for you to complete...")
            try:
                await page.wait_for_url("**/feed/**", timeout=60000)
                print("OK Login completed")
                await _save_session(context)
                return True
            except Exception:
                print("XX Login timed out")
                return False
        print(f"XX Login failed. Current URL: {current}")
        return False


async def is_session_valid(page: Page) -> bool:
    """Check if session is still active."""
    try:
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=10000)
        return "feed" in page.url or "mynetwork" in page.url
    except Exception:
        return False
