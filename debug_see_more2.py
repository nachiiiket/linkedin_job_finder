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
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        # Get first post element
        items = await page.query_selector_all('[role="listitem"]')
        if items:
            html = await items[0].inner_html()
            print("FULL HTML of first post:")
            print(html[:3000])
            print("\n\n---INNER TEXT---")
            txt = await items[0].inner_text()
            print(txt[:1000])

        # Check if email addresses exist in full page HTML
        body_html = await page.evaluate("document.body.innerHTML")
        import re
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', body_html)
        print(f"\n\nEmails found in raw HTML: {len(emails)}")
        for e in emails[:5]:
            print(f"  {e}")

        # Check if there's a "see more" or "...more" button somewhere
        see_more = await page.evaluate("""() => {
            const all = document.querySelectorAll('*');
            const results = [];
            for (const el of all) {
                if (el.children.length === 0 && el.textContent.trim().toLowerCase().includes('see more')) {
                    results.push(el.tagName + ' - ' + el.textContent.trim().slice(0, 50) + ' - visible:' + (el.offsetParent !== null));
                }
                if (el.children.length === 0 && el.textContent.includes('…more') || el.textContent.includes('...more')) {
                    results.push(el.tagName + ' - ' + el.textContent.trim().slice(0, 50) + ' - visible:' + (el.offsetParent !== null));
                }
            }
            return results.slice(0, 10);
        }""")
        print(f"\n'See more' elements found: {len(see_more)}")
        for s in see_more:
            print(f"  {s}")

        await browser.close()

asyncio.run(debug())
