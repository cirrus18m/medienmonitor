"""Stündlicher Lauf: Feeds abrufen, neue Schlagzeilen speichern, Themen zuordnen,
Ressorts und Blasen-Themen prüfen, daten.json und grafik.html (Grafik für
deutschlandmonitor.info) schreiben.

    uv run scripts/run_hourly.py --data-dir daten               # alles
    uv run scripts/run_hourly.py --data-dir daten --no-topics   # nur abrufen

Themen braucht Claude Code (``claude``) mit Anmeldung, siehe labeler.py. Zusammenlegen
doppelter Themen läuft bei ``--consolidate auto`` zu den UTC-Stunden 0, 6, 12 und 18.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from medienmonitor import bubbles, feeds, labeler, publish, render, store, topics

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
    parser.add_argument("--no-fetch", action="store_true", help="keine Feeds abrufen")
    parser.add_argument("--no-topics", action="store_true", help="keine KI-Zuordnung")
    parser.add_argument("--consolidate", choices=["auto", "ja", "nein"], default="auto")
    parser.add_argument(
        "--neu-zuordnen",
        metavar="THEMA",
        help="Thema (z. B. T114) auflösen; seine Schlagzeilen werden neu zugeordnet",
    )
    parser.add_argument(
        "--payload", type=Path, help="Pfad für daten.json (Standard: <data-dir>/daten.json)"
    )
    args = parser.parse_args()
    now = datetime.now(UTC)
    failed = False

    if args.neu_zuordnen:
        cleared = topics.dissolve(args.data_dir, args.neu_zuordnen.strip(), now)
        print(f"Thema {args.neu_zuordnen} aufgelöst, {cleared} Schlagzeilen wieder offen.")

    if not args.no_fetch:
        feed_list = feeds.load_feeds(args.feeds)
        headlines, errors = fetch_all(feed_list)
        new = store.append_new(args.data_dir, headlines)
        print(f"{len(feed_list)} Feeds, {len(headlines)} Schlagzeilen, {len(new)} neu.")
        for line in errors:
            print(f"  Fehler – {line}")
        # Fail only if (almost) everything broke, e.g. no network.
        failed = len(errors) > len(feed_list) // 2

    if not args.no_topics:
        try:
            model = labeler.from_env()
        except labeler.LabelerError as exc:
            print(f"Themen übersprungen: {exc}")
            failed = True
        else:
            result = topics.assign_new(args.data_dir, model, now)
            print(f"Themen: {result['zugeordnet']} von {result['offen']} Schlagzeilen zugeordnet.")
            for line in result["fehler"]:
                print(f"  Fehler – {line}")
            failed = failed or bool(result["fehler"])
            if args.consolidate == "ja" or (args.consolidate == "auto" and now.hour % 6 == 0):
                merged = topics.consolidate(args.data_dir, model, now)
                print(f"Zusammengelegt: {merged['zusammengelegt']} Themen.")
                for line in merged["fehler"]:
                    print(f"  Fehler – {line}")
            # Ressort of each topic, then the cross-check of the Blasen-Themen.
            topic_list = topics.TopicList.load(args.data_dir)
            classified = topics.classify_missing(topic_list, model, now)
            rows = publish.window_rows(args.data_dir, now, bubbles.BUBBLE_HOURS)
            checked = bubbles.cross_check(topic_list, rows, model, now)
            topic_list.save(args.data_dir)
            print(
                f"Ressorts: {classified['eingeordnet']} von {classified['offen']}; "
                f"Blasen-Themen geprüft: {checked['geprueft']}, "
                f"zusammengelegt: {checked['zusammengelegt']}."
            )
            for line in classified["fehler"] + checked["fehler"]:
                print(f"  Fehler – {line}")

    domains = {f.name: f.domain for f in feeds.load_feeds(args.feeds, only_active=False)}
    payload = publish.build_payload(args.data_dir, now, domains)
    # second window for the filter "nur heute": since midnight in Berlin
    payload["heute"] = publish.build_payload(
        args.data_dir, now, domains, start=publish.start_of_day(now), categories=False
    )
    payload_path = args.payload or args.data_dir / "daten.json"
    publish.write_payload(payload, payload_path)
    render.write_html(payload, payload_path.with_name("grafik.html"))
    print(
        f"daten.json: {len(payload['themen'])} Themen, "
        f"{payload['artikel_zugeordnet']} von {payload['artikel_gesamt']} Artikeln "
        "(24 h) zugeordnet."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
