import asyncio
from playwright.async_api import Page
from .browser import human_delay, human_type


async def send_connection(
    page: Page,
    profile_url: str,
    name: str = "",
    position: str = "",
    company: str = "",
    config: dict = None,
) -> bool:
    """
    Send a connection request to a LinkedIn profile.
    Returns True if request was sent.
    """
    config = config or {}
    actions = config.get("actions", {})
    message_template = actions.get(
        "connection_message",
        "Hi {name}, I came across your post about the {position} role. I'd love to connect!"
    )

    # Personalise message
    message = message_template.format(
        name=name.split(" ")[0] if name else "there",
        position=position or "role",
        company=company or "your company",
    )

    try:
        await page.goto(profile_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Find Connect button (may be inside "More" menu)
        connect_btn = None

        # Direct connect button
        try:
            btn = page.locator("button:has-text('Connect')").first
            if await btn.is_visible(timeout=2000):
                connect_btn = btn
        except Exception:
            pass

        # If not found, try "More" >> Connect
        if not connect_btn:
            try:
                more_btn = page.locator("button:has-text('More')").first
                await more_btn.click()
                await asyncio.sleep(1)
                connect_btn = page.locator(
                    "div[aria-label='More actions'] li-icon[type='connect'] ~ span"
                ).first
            except Exception:
                pass

        if not connect_btn:
            print(f"  XX Connect button not found on {profile_url}")
            return False

        await connect_btn.click()
        await asyncio.sleep(1.5)

        # Add a note
        try:
            add_note = page.locator("button:has-text('Add a note')").first
            if await add_note.is_visible(timeout=2000):
                await add_note.click()
                await asyncio.sleep(1)
                textarea = page.locator("textarea#custom-message, textarea[name='message']").first
                await textarea.fill("")
                for char in message:
                    await textarea.type(char, delay=30)
                await asyncio.sleep(0.5)
        except Exception:
            pass  # Send without note if modal doesn't appear

        # Send
        send_btn = page.locator("button:has-text('Send'), button:has-text('Send now')").first
        if await send_btn.is_visible(timeout=2000):
            await send_btn.click()
            await asyncio.sleep(1)
            print(f"  OK Connection request sent to {name or profile_url}")
            return True

        print(f"  XX Send button not found")
        return False

    except Exception as e:
        print(f"  XX Connection error for {profile_url}: {e}")
        return False
