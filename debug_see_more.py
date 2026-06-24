import asyncio, json, urllib.parse
from playwright.async_api import async_playwright

async def debug():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        config = json.load(open("config.json"))
        creds = config["credentials"]
        await page.goto("https://www.linkedin.com/login", wait_until="load")
        await asyncio.sleep(3)
        await page.get_by_role("textbox", name="Email or phone").fill(creds["email"])
        await page.get_by_role("textbox", name="Password").fill(creds["password"])
        await page.get_by_role("button", name="Sign in", exact=True).click()
        try: await page.wait_for_url("**/feed/**", timeout=20000)
        except: pass

        query = '("Hiring" AND "AI/ML Engineer")'
        encoded = urllib.parse.quote(query)
        url = f"https://www.linkedin.com/search/results/content/?keywords={encoded}&origin=GLOBAL_SEARCH_HEADER&sortBy=%22date_posted%22"
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # Find "see more" buttons/links
        for sel in [
            "button:has-text('see more')",
            "button:has-text('…more')",
            "button:has-text('...more')",
            "span:has-text('see more')",
            "a:has-text('see more')",
            "[aria-label*='more']",
            "button.show-more",
            ".feed-shared-inline-show-more-text__button",
            "[data-linger-trigger*='more']",
        ]:
            try:
                els = await page.query_selector_all(sel)
                print(f"{sel}: {len(els)}")
                for el in els[:3]:
                    text = await el.inner_text()
                    visible = await el.is_visible()
                    tag = await el.evaluate("el => el.tagName")
                    print(f"   -> <{tag}> visible={visible} text='{text[:60]}'")
            except Exception as e:
                print(f"{sel}: ERROR {e}")

        # Also search for any element containing "see more" or "…more"
        print("\n--- Text search for 'see more' ---")
        body = await page.inner_text("body")
        idx = body.lower().find("see more")
        if idx >= 0:
            print(f"Found 'see more' at index {idx}")
            print(f"Context: ...{body[max(0,idx-50):idx+100]}...")

        idx2 = body.find("…more")
        if idx2 >= 0:
            print(f"\nFound '…more' at index {idx2}")
            print(f"Context: ...{body[max(0,idx2-50):idx2+100]}...")

        await browser.close()

asyncio.run(debug())
