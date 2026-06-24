import asyncio
from playwright.async_api import Page
from .browser import human_delay, human_type


async def easy_apply(page: Page, job_url: str, profile: dict, config: dict) -> bool:
    """
    Attempt Easy Apply on a job. profile dict should have:
    phone, resume_path (optional for upload), cover_letter (optional).
    Returns True if submitted successfully.
    """
    try:
        await page.goto(job_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Click Easy Apply
        apply_btn = page.locator(".jobs-apply-button--top-card").first
        btn_text = await apply_btn.inner_text(timeout=3000)
        if "easy apply" not in btn_text.lower():
            print("  XX Not Easy Apply")
            return False

        await apply_btn.click()
        await asyncio.sleep(2)

        # Walk through modal steps
        max_steps = 10
        for step in range(max_steps):
            # Check if submitted
            try:
                success = page.locator(".jobs-easy-apply-content h3:has-text('application was sent')")
                if await success.count() > 0:
                    print("  OK Application submitted")
                    return True
            except Exception:
                pass

            # Fill phone if field exists and empty
            try:
                phone_field = page.locator("input[name*='phone'], input[id*='phone']").first
                if await phone_field.is_visible(timeout=1000):
                    existing = await phone_field.input_value()
                    if not existing and profile.get("phone"):
                        await human_type(page, "input[name*='phone']", profile["phone"])
            except Exception:
                pass

            # Handle resume upload if field present
            try:
                upload = page.locator("input[type='file']").first
                if await upload.is_visible(timeout=500) and profile.get("resume_path"):
                    await upload.set_input_files(profile["resume_path"])
                    await asyncio.sleep(1)
            except Exception:
                pass

            # Handle Yes/No radio questions (default to "Yes")
            try:
                radios = page.locator("fieldset .fb-radio-button input[type='radio']")
                count = await radios.count()
                if count > 0:
                    await radios.first.check()
            except Exception:
                pass

            # Handle numeric input (e.g. years of experience) - fill "0" if empty
            try:
                num_inputs = page.locator("input[type='text'].fb-single-line-text__input")
                n_count = await num_inputs.count()
                for i in range(n_count):
                    inp = num_inputs.nth(i)
                    val = await inp.input_value()
                    if not val:
                        await inp.fill("0")
            except Exception:
                pass

            # Next / Submit button
            next_btn = None
            for label in ["Submit application", "Next", "Review", "Continue"]:
                try:
                    btn = page.locator(f"button:has-text('{label}')").first
                    if await btn.is_visible(timeout=1000):
                        next_btn = btn
                        break
                except Exception:
                    pass

            if next_btn:
                await next_btn.click()
                await asyncio.sleep(2)
            else:
                # No more buttons, might be done or stuck
                break

        # Check once more for success
        try:
            success = page.locator("h3:has-text('application was sent'), h2:has-text('Done')")
            if await success.count() > 0:
                print("  OK Application submitted")
                return True
        except Exception:
            pass

        print("  !! Apply flow ended - verify manually")
        return False

    except Exception as e:
        print(f"  XX Easy Apply error: {e}")
        return False


async def close_apply_modal(page: Page):
    """Close any open apply modal."""
    try:
        dismiss = page.locator("button[aria-label='Dismiss'], button:has-text('Discard')").first
        if await dismiss.is_visible(timeout=1000):
            await dismiss.click()
            await asyncio.sleep(1)
            confirm = page.locator("button:has-text('Discard')").first
            if await confirm.is_visible(timeout=1000):
                await confirm.click()
    except Exception:
        pass
