"""
LinkedIn Job Bot - main entry point.
Usage: python main.py [--mode jobs|posts|both] [--apply] [--connect]
"""

import asyncio
import json
import argparse
import os
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

warnings.filterwarnings("ignore", message="unclosed transport")

import bot
from tracker import CSVTracker
from tracker.xlsx_writer import export_csv_to_xlsx

console = Console()

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

class _Tee:
    def __init__(self, filepath: str):
        self.file = open(filepath, "w", encoding="utf-8")
        self.stdout = sys.stdout

    def write(self, text: str):
        try:
            self.stdout.write(text)
        except UnicodeEncodeError:
            self.stdout.write(text.encode(self.stdout.encoding or "utf-8", errors="replace").decode(self.stdout.encoding or "utf-8"))
        self.file.write(_ANSI_RE.sub("", text))
        self.file.flush()

    def flush(self):
        self.stdout.flush()
        self.file.flush()


def load_config(path: str = "config.json") -> dict:
    with open(path, "r") as f:
        return json.load(f)


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]LinkedIn Job Bot[/bold cyan]\n"
        "[dim]Personal automation - jobs tracker + CSV dedup[/dim]",
        border_style="cyan"
    ))


def print_stats(tracker: CSVTracker):
    stats = tracker.get_stats()
    table = Table(title="Session Summary", show_header=False, border_style="green")
    table.add_column("Metric", style="bold")
    table.add_column("Count", style="cyan")
    table.add_row("Jobs tracked", str(stats["total"]))
    table.add_row("Applied", str(stats["applied"]))
    table.add_row("Connections sent", str(stats["connected"]))
    console.print(table)


async def run_job_search(page, config: dict, tracker: CSVTracker, apply: bool, connect: bool):
    """Run Jobs page search for all keyword × location combos."""
    search_cfg = config.get("search", {})
    keywords = search_cfg.get("keywords", [])
    locations = search_cfg.get("locations", [])
    easy_apply_only = search_cfg.get("easy_apply_only", True)
    posted_days = search_cfg.get("posted_within_days", 7)
    max_jobs = search_cfg.get("max_jobs_per_run", 50)
    target_titles = config.get("filters", {}).get("target_poster_titles", [])
    actions = config.get("actions", {})
    hunter_key = actions.get("hunter_api_key", "")

    total_found = 0

    for keyword in keywords:
        for location in locations:
            if total_found >= max_jobs:
                break

            console.print(f"\n[bold]Searching:[/bold] {keyword} in {location}")

            url = bot._build_job_search_url(keyword, location, easy_apply_only, posted_days)
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            page_num = 1
            while total_found < max_jobs:
                job_ids = await bot.get_job_ids_on_page(page)
                console.print(f"  Page {page_num}: found {len(job_ids)} job cards")

                for jid in job_ids:
                    if total_found >= max_jobs:
                        break

                    if tracker.is_duplicate(job_id=jid):
                        console.print(f"  [dim]-> Skipping duplicate job {jid}[/dim]")
                        continue

                    clicked = await bot.click_job_card(page, jid)
                    if not clicked:
                        continue

                    details = await bot.extract_job_details(page, jid)

                    poster_title = details.get("poster_title", "")
                    if target_titles and not bot.matches_target_poster(poster_title, target_titles):
                        console.print(f"  [dim]-> Skipping - poster title: {poster_title or 'unknown'}[/dim]")
                        continue

                    if tracker.is_duplicate(
                        poster_name=details.get("poster_name", ""),
                        position=details.get("position", ""),
                    ):
                        console.print(f"  [dim]-> Duplicate: {details.get('position')} by {details.get('poster_name')}[/dim]")
                        continue

                    if hunter_key and details.get("company"):
                        domain = bot.guess_company_domain(details["company"])
                        first, last = bot.split_name(details.get("poster_name", ""))
                        if first and domain:
                            email = bot.find_email_hunter(first, last, domain, hunter_key)
                            details["email"] = email

                    saved = tracker.save(details)
                    if not saved:
                        continue

                    total_found += 1
                    pos = details.get("position", "?")
                    co = details.get("company", "?")
                    pname = details.get("poster_name", "unknown")
                    email_info = f" | email: {details.get('email', '')[:30]}" if details.get("email") else ""
                    console.print(f"  [green]OK[/green] [{total_found}] {pos} @ {co} | by {pname}{email_info}")

                    if apply and actions.get("auto_easy_apply"):
                        is_ea = await bot.has_easy_apply(page)
                        if is_ea:
                            profile = config.get("profile", {})
                            success = await bot.easy_apply(
                                page, details["job_url"], profile, config
                            )
                            if success:
                                tracker.update_field(jid, "applied", "Yes")
                                details["applied"] = "Yes"
                            await bot.close_apply_modal(page)

                    if connect and actions.get("send_connection_request"):
                        profile_url = details.get("poster_profile_url", "")
                        if profile_url:
                            sent = await bot.send_connection(
                                page,
                                profile_url,
                                name=details.get("poster_name", ""),
                                position=details.get("position", ""),
                                company=details.get("company", ""),
                                config=config,
                            )
                            if sent:
                                tracker.update_field(jid, "connection_sent", "Yes")

                    await bot.human_delay(config)

                has_next = await bot.load_next_page(page, page_num)
                if not has_next:
                    break
                page_num += 1
                await asyncio.sleep(3)

    console.print(f"\n[bold]Job search complete:[/bold] {total_found} jobs found")


async def _save_posts_to_csv(posts: list[dict], tracker: CSVTracker, config: dict, connect: bool, page) -> int:
    """Save parsed posts to CSV, optionally send connection requests. Returns count saved."""
    actions = config.get("actions", {})
    count = 0
    for post in posts:
        if tracker.is_duplicate(
            job_id=post.get("job_id", ""),
            poster_name=post.get("poster_name", ""),
            position=post.get("position", ""),
        ):
            continue

        saved = tracker.save(post)
        if saved:
            count += 1
            pname = post.get("poster_name", "?")
            pos = post.get("position", "?")
            co = post.get("company", "?")
            loc = post.get("location", "?")
            email_info = f" | email: {post.get('email', '')[:30]}" if post.get("email") else ""
            console.print(f"  [green]OK[/green] {pos} @ {co} ({loc}) by {pname}{email_info}")

            if connect and actions.get("send_connection_request"):
                profile_url = post.get("poster_profile_url", "")
                if profile_url:
                    await bot.send_connection(
                        page, profile_url,
                        name=pname, position=pos, company=co, config=config,
                    )
    return count


async def run_post_search(page, config: dict, tracker: CSVTracker, connect: bool):
    """Search LinkedIn feed posts, parse with regex, save to CSV."""
    actions = config.get("actions", {})

    variants = bot.generate_search_variants(config)
    if not variants:
        console.print("[yellow]No search variants generated[/yellow]")
        return

    for i, variant in enumerate(variants):
        console.print(f"\n[bold]Search {i+1}/{len(variants)}:[/bold] {variant['label']}")
        console.print(f"  [dim]Query: {variant['query'][:100]}[/dim]")

        markdown = await bot.get_page_markdown(page, variant["query"], variant["sort_by"])
        md_path = bot.save_markdown_to_file(markdown, variant["label"])
        if not md_path:
            continue

        results = bot.parse_md_file(md_path)
        if not results:
            console.print(f"  [dim]No extractable posts from '{variant['label']}'[/dim]")
            continue

        saved = await _save_posts_to_csv(results, tracker, config, connect, page)
        console.print(f"  [green]-> Saved {saved} posts[/green]")

    tracker.deduplicate()
    console.print(f"\n[bold]Post search complete[/bold]")


async def main(mode: str, apply: bool, connect: bool):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    log_path = str(logs_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    sys.stdout = _Tee(log_path)
    sys.stderr = sys.stdout

    print(f"Log file: {log_path}")
    print_banner()

    config = load_config()
    config["credentials"] = {
        "email":    os.environ.get("LINKEDIN_EMAIL") or config.get("credentials", {}).get("email", ""),
        "password": os.environ.get("LINKEDIN_PASSWORD") or config.get("credentials", {}).get("password", ""),
    }
    csv_path = config.get("output", {}).get("csv_file", "job_tracker.csv")
    tracker = CSVTracker(csv_path)

    console.print(f"[dim]CSV:[/dim] {csv_path}")
    console.print(f"[dim]Mode:[/dim] {mode} | Apply: {apply} | Connect: {connect}\n")

    browser, context, page = await bot.launch_browser(config)

    try:
        ok = await bot.login(page, context, config)
        if not ok:
            console.print("[red]Login failed. Exiting.[/red]")
            return

        if mode in ("jobs", "both"):
            await run_job_search(page, config, tracker, apply, connect)

        if mode in ("posts", "both"):
            await run_post_search(page, config, tracker, connect)

        # Remove any duplicates accumulated in CSV
        tracker.deduplicate()

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        raise
    finally:
        print_stats(tracker)

        xlsx_path = export_csv_to_xlsx(csv_path)
        if xlsx_path:
            console.print(f"  [dim]XLSX:[/dim] {xlsx_path}")

        await context.close()
        await browser.close()
        console.print(f"\n[green]Done.[/green] Results saved to [bold]{csv_path}[/bold]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedIn Job Bot")
    parser.add_argument(
        "--mode",
        choices=["jobs", "posts", "both"],
        default="both",
        help="Search jobs page, feed posts, or both (default: both)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Enable Easy Apply (must set auto_easy_apply=true in config)",
    )
    parser.add_argument(
        "--connect",
        action="store_true",
        help="Send connection requests to posters",
    )
    args = parser.parse_args()
    asyncio.run(main(args.mode, args.apply, args.connect))
