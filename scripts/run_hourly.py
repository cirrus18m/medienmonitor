"""Stündlicher Lauf: Feeds abrufen und neue Schlagzeilen speichern.

    uv run scripts/run_hourly.py --data-dir daten

Weitere Schritte (Themen, daten.json, Upload) folgen laut Plan.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from medienmonitor import feeds, store

ROOT = Path(__file__).resolve().parent.parent


def fetch_all(feed_list: list[feeds.Feed]) -> tuple[list[feeds.Headline], list[str]]:
    now = datetime.now(UTC)
    errors: list[str] = []
    headlines: list[feeds.Headline] = []
    with feeds.http_client() as client:

        def one(feed: feeds.Feed):
            try:
                return feed, feeds.parse_feed(feeds.fetch_feed(feed, client), feed, now), None
            except Exception as exc:  # one broken feed must not stop the run
                return feed, [], f"{type(exc).__name__}: {str(exc).splitlines()[0]}"

        with ThreadPoolExecutor(max_workers=8) as pool:
            for feed, items, error in pool.map(one, feed_list):
                if error:
                    errors.append(f"{feed.name}: {error}")
                elif not items:
                    errors.append(f"{feed.name}: keine Einträge")
                headlines.extend(items)
    return headlines, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "daten")
    parser.add_argument("--feeds", type=Path, default=ROOT / "feeds.yaml")
    args = parser.parse_args()

    feed_list = feeds.load_feeds(args.feeds)
    headlines, errors = fetch_all(feed_list)
    new = store.append_new(args.data_dir, headlines)
    print(f"{len(feed_list)} Feeds, {len(headlines)} Schlagzeilen, {len(new)} neu.")
    for line in errors:
        print(f"  Fehler – {line}")
    # Fail only if (almost) everything broke, e.g. no network.
    return 1 if len(errors) > len(feed_list) // 2 else 0


if __name__ == "__main__":
    sys.exit(main())
