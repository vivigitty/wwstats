"""Bulk-download CricHeroes scorecards for a team, month by month.

Flow
----
1. Launches Chrome with remote debugging against a dedicated profile in .chrome-profile
   (Chrome 136+ blocks remote debugging on the default profile).
2. Prompts you to log in if CricHeroes isn't authenticated yet. The profile is reused,
   so this is a one-off.
3. Opens "My Matches" and collects every match card.
4. Keeps the matches for TEAM_NAME whose date falls in the configured window.
5. For each one: opens it, switches to the Scorecard tab, clicks "Download Scorecard".

Configure the window below, or override on the command line:

    python download_scorecard.py                      # uses the constants below
    python download_scorecard.py --from 2026-01 --to 2026-09
    python download_scorecard.py --from 2026-01 --dry-run
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------- configuration
TEAM_NAME = "Weekend Wickets"

# Inclusive download window. Bump END_* as the season progresses.
START_YEAR, START_MONTH = 2026, 1
END_YEAR, END_MONTH = 2026, 12

CDP_PORT = 9222
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
DOWNLOAD_DIR = Path(__file__).parent / "Match Data"
# Chrome 136+ refuses --remote-debugging-port on the default profile, so use our own.
# It persists between runs, meaning you only have to log in to CricHeroes once.
PROFILE_DIR = Path(__file__).parent / ".chrome-profile"
MY_MATCHES_URL = "https://cricheroes.com/my-matches"
# ------------------------------------------------------------------------------

MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}
MONTHS.update({name[:3]: num for name, num in list(MONTHS.items())})

DATE_RE = re.compile(
    r"(\d{1,2})\s*(?:st|nd|rd|th)?[\s,\-/]*"
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,\-/]*"
    r"(\d{2,4})",
    re.I,
)
ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
DOWNLOAD_RE = re.compile(r"download\s*scorecard", re.I)


def month_key(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def parse_window(text: str, label: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})", text.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"--{label} must look like 2026-01, got {text!r}")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        raise argparse.ArgumentTypeError(f"--{label} month out of range: {text!r}")
    return year, month


def parse_card_date(text: str) -> datetime | None:
    iso = ISO_DATE_RE.search(text)
    if iso:
        return datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    match = DATE_RE.search(text)
    if not match:
        return None
    month = MONTHS.get(match.group(2)[:3].lower())
    if not month:
        return None
    year = int(match.group(3))
    if year < 100:  # CricHeroes renders "26-Sep-26"
        year += 2000
    try:
        return datetime(year, month, int(match.group(1)))
    except ValueError:
        return None


# ------------------------------------------------------------------- browser


def cdp_is_live(port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2):
            return True
    except Exception:
        return False


def launch_chrome(port: int) -> bool:
    exe = next((p for p in CHROME_PATHS if Path(p).exists()), None)
    if not exe:
        return False
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Starting {Path(exe).name} with remote debugging on port {port}...")
    print(f"Profile: {PROFILE_DIR}")
    subprocess.Popen(
        [
            exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={PROFILE_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            MY_MATCHES_URL,
        ]
    )
    for _ in range(30):
        if cdp_is_live(port):
            return True
        time.sleep(1)
    return False


def pick_page(browser) -> Page:
    pages = [p for ctx in browser.contexts for p in ctx.pages]
    for page in pages:
        if "cricheroes.com" in page.url:
            return page
    if pages:
        return pages[-1]
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    return ctx.new_page()


def ensure_logged_in(page: Page) -> None:
    """Block until My Matches actually renders match cards for a signed-in user."""
    while True:
        if "/my-matches" not in page.url:
            page.goto(MY_MATCHES_URL, wait_until="domcontentloaded")
        try:
            page.wait_for_selector('a[href*="/scorecard/"]', timeout=25_000)
            return
        except PlaywrightTimeout:
            pass

        signed_out = page.get_by_text(
            re.compile(r"sign in to continue|log in to continue", re.I)
        ).count()
        reason = (
            "CricHeroes is showing the sign-in screen."
            if signed_out
            else "No match cards are visible yet (you may not be signed in)."
        )

        print(
            f"\n{reason}\n"
            "Sign in to CricHeroes in the Chrome window this script opened, wait until\n"
            "your My Matches list is showing, then return here.\n"
            "This profile is saved, so you only need to do this once."
        )
        input("Press Enter once your matches are visible... ")
        page.goto(MY_MATCHES_URL, wait_until="domcontentloaded")


# --------------------------------------------------------------- match listing


def load_all_matches(page: Page, max_rounds: int = 40) -> None:
    """Exhaust infinite scroll / 'Load More' so every match card is in the DOM."""
    previous = -1
    for _ in range(max_rounds):
        more = page.get_by_role("button", name=re.compile(r"load\s*more|show\s*more", re.I))
        if more.count() and more.first.is_visible():
            more.first.click()
        else:
            page.mouse.wheel(0, 20_000)
        page.wait_for_timeout(1500)
        count = page.locator('a[href*="/scorecard/"]').count()
        if count == previous:
            break
        previous = count


_CARD_SCRIPT = """
() => {
  const out = [];
  const seen = new Set();
  const dateish = /\\d{1,2}[\\s,\\-\\/]*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i;
  for (const a of document.querySelectorAll('a[href*="/scorecard/"]')) {
    const href = a.href.split('?')[0];
    if (seen.has(href)) continue;
    seen.add(href);
    // Climb from the link until we reach the element that carries the match date.
    let el = a, text = '';
    for (let i = 0; i < 8 && el; i++) {
      const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
      if (t.length > 600) break;
      text = t;
      if (dateish.test(t)) break;
      el = el.parentElement;
    }
    out.push({ href, text });
  }
  return out;
}
"""


def collect_matches(page: Page, team: str) -> list[dict]:
    """Return {url, date, label} for every match card linking to a scorecard."""
    cards = page.evaluate(_CARD_SCRIPT)
    matches = []
    for card in cards:
        text = card["text"]
        matches.append(
            {
                "url": card["href"],
                "date": parse_card_date(text),
                "label": text[:160],
                "team_match": team.lower() in text.lower(),
            }
        )
    return matches


def in_window(match: dict, start: tuple[int, int], end: tuple[int, int]) -> bool:
    date = match["date"]
    if date is None:
        return False
    key = month_key(date.year, date.month)
    return month_key(*start) <= key <= month_key(*end)


# ------------------------------------------------------------------- scorecard


def open_scorecard_tab(page: Page) -> None:
    for locator in (
        page.get_by_role("tab", name=re.compile(r"scorecard", re.I)),
        page.get_by_role("link", name=re.compile(r"^\s*scorecard\s*$", re.I)),
        page.get_by_text(re.compile(r"^\s*scorecard\s*$", re.I)),
    ):
        if locator.count():
            try:
                locator.first.click(timeout=5000)
                page.wait_for_timeout(2000)
                return
            except PlaywrightError:
                continue
    # Already on the scorecard route; nothing to click.


def find_download_button(page: Page):
    """Return the first visible 'Download Scorecard' control, or None."""
    for locator in (
        page.get_by_role("button", name=DOWNLOAD_RE),
        page.get_by_role("link", name=DOWNLOAD_RE),
        page.get_by_text(DOWNLOAD_RE),
    ):
        try:
            count = locator.count()
        except PlaywrightError:
            continue
        for i in range(count):
            item = locator.nth(i)
            try:
                if item.is_visible():
                    return item
            except PlaywrightError:
                continue
    return None


def download_scorecard(page: Page, attempts: int = 3) -> Path | None:
    """Click 'Download Scorecard', retrying through lazy rendering and stale clicks."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, attempts + 1):
        button = find_download_button(page)
        if button is None:
            # The button often renders only after the scorecard body is scrolled in.
            for _ in range(3):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1200)
                button = find_download_button(page)
                if button is not None:
                    break

        if button is None:
            if attempt < attempts:
                print(f"    button not found, retrying ({attempt}/{attempts - 1})")
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                open_scorecard_tab(page)
                continue
            return None

        try:
            button.scroll_into_view_if_needed()
            with page.expect_download(timeout=60_000) as info:
                button.click(timeout=10_000)
            download = info.value
        except (PlaywrightTimeout, PlaywrightError) as exc:
            if attempt < attempts:
                print(f"    click failed ({type(exc).__name__}), retrying")
                page.wait_for_timeout(2000)
                continue
            return None

        target = DOWNLOAD_DIR / (download.suggested_filename or "scorecard.pdf")
        if target.exists():
            target = target.with_name(f"{target.stem}-{int(time.time())}{target.suffix}")
        download.save_as(target)
        return target

    return None


# ------------------------------------------------------------------------ main


def run_downloads(page: Page, matches: list[dict], retries: int) -> list[dict]:
    """Download each match's scorecard; return the ones that didn't produce a file."""
    failed = []
    for i, m in enumerate(matches, start=1):
        print(f"[{i}/{len(matches)}] {m['date']:%Y-%m-%d} {m['url']}")
        try:
            page.goto(m["url"], wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            open_scorecard_tab(page)
            saved = download_scorecard(page, attempts=retries)
        except PlaywrightError as exc:
            print(f"    failed: {exc}")
            failed.append(m)
            continue
        if saved:
            print(f"    saved: {saved}")
        else:
            print("    no Download Scorecard button found")
            failed.append(m)
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", help="First month to download, e.g. 2026-01")
    parser.add_argument("--to", dest="end", help="Last month to download, e.g. 2026-09")
    parser.add_argument("--team", default=TEAM_NAME)
    parser.add_argument("--port", type=int, default=CDP_PORT)
    parser.add_argument(
        "--retries", type=int, default=3, help="Attempts per match (default 3)"
    )
    parser.add_argument("--dry-run", action="store_true", help="List matches, download nothing")
    args = parser.parse_args()

    start = parse_window(args.start, "from") if args.start else (START_YEAR, START_MONTH)
    end = parse_window(args.end, "to") if args.end else (END_YEAR, END_MONTH)
    if month_key(*end) < month_key(*start):
        parser.error("--to must not be earlier than --from")

    print(f"Team   : {args.team}")
    print(f"Window : {start[0]}-{start[1]:02d} .. {end[0]}-{end[1]:02d}")

    with sync_playwright() as pw:
        if not cdp_is_live(args.port) and not launch_chrome(args.port):
            print(
                f"No browser listening on port {args.port}. Launch one manually with:\n"
                f'  & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
                f'--remote-debugging-port={args.port} --user-data-dir="{PROFILE_DIR}"',
                file=sys.stderr,
            )
            return 1

        try:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
        except PlaywrightError as exc:
            print(f"Could not attach to the browser: {exc}", file=sys.stderr)
            return 1

        page = pick_page(browser)
        page.bring_to_front()
        ensure_logged_in(page)

        load_all_matches(page)
        matches = collect_matches(page, args.team)
        wanted = [m for m in matches if m["team_match"] and in_window(m, start, end)]
        wanted.sort(key=lambda m: m["date"])

        print(f"\nFound {len(matches)} matches, {len(wanted)} in the window.")
        if not matches:
            print(
                "No scorecard links were found on the page. Check that the Chrome window\n"
                "is showing your My Matches list, then re-run."
            )
        for m in wanted:
            print(f"  {m['date']:%Y-%m-%d}  {m['label']}")

        undated = [m for m in matches if m["date"] is None and m["team_match"]]
        if undated:
            print(f"({len(undated)} cards had no readable date and were skipped.)")
            if args.dry_run:
                print("\nSample card text, to fix date parsing:")
                for m in undated[:5]:
                    print(f"  {m['url']}\n    {m['label']!r}")

        if args.dry_run or not wanted:
            return 0

        print()
        failed = run_downloads(page, wanted, args.retries)

        if failed:
            print(f"\nRetrying {len(failed)} match(es) that failed the first pass...")
            failed = run_downloads(page, failed, args.retries)

        if failed:
            print(f"\n{len(failed)} match(es) still failed:")
            for m in failed:
                print(f"  {m['date']:%Y-%m-%d} {m['url']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
