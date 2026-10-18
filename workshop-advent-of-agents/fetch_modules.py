"""Download Advent of Agents Season 3 daily modules as Markdown.

Each day is published at https://adventofagents.com/2026/10/<DD>.md and saved
as MODULE-<day>.md next to this script (same format as MODULE-1.md).

Usage:
    python fetch_modules.py            # days 2..16
    python fetch_modules.py 1 16       # custom range (inclusive)
    python fetch_modules.py 5 5 --force
"""

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://adventofagents.com/2026/10/{day:02d}.md"
OUT_DIR = Path(__file__).resolve().parent
USER_AGENT = "Mozilla/5.0 (advent-of-agents-fetcher)"


def fetch(url: str, retries: int = 3) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "markdown" not in content_type:
                    raise ValueError(f"unexpected Content-Type {content_type!r}")
                return resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries:
                raise
            print(f"  retry {attempt}/{retries - 1} after error: {exc}")
            time.sleep(2 * attempt)
    raise RuntimeError("unreachable")


def check_day(markdown: str, day: int) -> None:
    match = re.search(r"^day:\s*(\d+)\s*$", markdown, re.MULTILINE)
    if not match or int(match.group(1)) != day:
        raise ValueError(f"front matter does not declare day: {day}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("start", nargs="?", type=int, default=2)
    parser.add_argument("end", nargs="?", type=int, default=16)
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    args = parser.parse_args()

    failures = []
    for day in range(args.start, args.end + 1):
        url = BASE_URL.format(day=day)
        out = OUT_DIR / f"MODULE-{day}.md"
        if out.exists() and not args.force:
            print(f"[skip] {out.name} already exists")
            continue
        try:
            markdown = fetch(url)
            check_day(markdown, day)
        except Exception as exc:
            print(f"[fail] day {day:02d} ({url}): {exc}")
            failures.append(day)
            continue
        out.write_text(markdown, encoding="utf-8")
        title = re.search(r'^title:\s*"?(.*?)"?\s*$', markdown, re.MULTILINE)
        print(f"[ok]   {out.name} <- {url} ({title.group(1) if title else '?'})")

    if failures:
        print(f"Failed days: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
