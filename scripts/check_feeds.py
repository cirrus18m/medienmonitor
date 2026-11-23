"""Prüft alle Feeds aus feeds.yaml und zeigt je Quelle Status und Zahl der Einträge.

uv run scripts/check_feeds.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from run_hourly import fetch_all

from medienmonitor import feeds

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    feed_list = feeds.load_feeds(ROOT / "feeds.yaml")
    headlines, errors = fetch_all(feed_list)
    counts: dict[str, int] = {}
    for h in headlines:
        counts[h.quelle] = counts.get(h.quelle, 0) + 1
    failed = {line.split(":", 1)[0]: line for line in errors}
    for feed in feed_list:
        mark = "FEHLER" if feed.name in failed else "ok    "
        note = failed.get(feed.name, "").split(":", 1)[-1].strip()
        check = " (pruefen)" if feed.pruefen else ""
        print(f"{mark} {feed.name:<22}{counts.get(feed.name, 0):>4} Einträge{check} {note}")
    print(f"\n{len(feed_list) - len(failed)} von {len(feed_list)} Feeds liefern Einträge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
