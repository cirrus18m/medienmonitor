"""Build daten.json for the page "Medienmonitor": topics of the last 24 hours by group.

Shares are per group: articles of the group on the topic / all articles of the group in
the window (in percent), so groups with many feeds do not dominate. The same holds per
medium ("medien", "anzahl_medium"): articles of the medium on the topic / all its articles.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from medienmonitor import store
from medienmonitor.topics import OTHER, TopicList

SCHEMA = 1
WINDOW_HOURS = 24
MIN_ARTICLES = 5
MIN_SOURCES = 2
MAX_TOPICS = 40
CAMPS = ("links", "mitte", "rechts", "alternativ")
SPECTRA = ("links", "mitte-links", "mitte", "mitte-rechts", "rechts", "unklar")
BERLIN = ZoneInfo("Europe/Berlin")


def _time(row: dict) -> str:
    """Publication time if known and not in the future, else time of fetching."""
    published = row.get("veroeffentlicht")
    if published and published <= row["abgerufen"]:
        return published
    return row["abgerufen"]


def window_rows(data_dir: Path, now: datetime, hours: int = WINDOW_HOURS) -> list[dict]:
    limit = (now - timedelta(hours=hours)).astimezone(UTC).isoformat(timespec="seconds")
    days = hours // 24 + 2
    return [row for row in store.read_days(data_dir, now.date(), days) if _time(row) >= limit]


def _shares(counts: Counter, totals: Counter, keys: tuple[str, ...]) -> dict[str, float]:
    return {k: round(100 * counts[k] / totals[k], 1) if totals[k] else 0.0 for k in keys}


def build_payload(data_dir: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    topics = TopicList.load(data_dir)
    rows = window_rows(data_dir, now)
    per_camp = Counter(row["lager"] for row in rows)
    per_spectrum = Counter(row["spektrum"] for row in rows)
    media: dict[str, dict] = {}
    for row in rows:
        medium = media.setdefault(
            row["quelle"],
            {
                "name": row["quelle"],
                "lager": row["lager"],
                "spektrum": row["spektrum"],
                "land": row["land"],
                "artikel": 0,
            },
        )
        medium["artikel"] += 1

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        topic_id = topics.resolve(row.get("thema_id"))
        if topic_id and topic_id != OTHER and topic_id in topics.themen:
            grouped[topic_id].append(row)

    entries = []
    for topic_id, items in grouped.items():
        if len(items) < MIN_ARTICLES or len({r["quelle"] for r in items}) < MIN_SOURCES:
            continue
        camps = Counter(r["lager"] for r in items)
        spectra = Counter(r["spektrum"] for r in items)
        items.sort(key=_time, reverse=True)
        entries.append(
            {
                "id": topic_id,
                "name": topics.themen[topic_id]["name"],
                "beschreibung": topics.themen[topic_id]["beschreibung"],
                "anzahl_gesamt": len(items),
                "quellen": len({r["quelle"] for r in items}),
                "anzahl": {"lager": dict(camps), "spektrum": dict(spectra)},
                "anzahl_medium": dict(Counter(r["quelle"] for r in items)),
                "anteil_pct": {
                    "lager": _shares(camps, per_camp, CAMPS),
                    "spektrum": _shares(spectra, per_spectrum, SPECTRA),
                },
                "artikel": [
                    {
                        "quelle": r["quelle"],
                        "lager": r["lager"],
                        "spektrum": r["spektrum"],
                        "titel": r["titel"],
                        "url": r["url"],
                        "zeit": _time(r),
                    }
                    for r in items
                ],
            }
        )
    entries.sort(key=lambda e: (e["anzahl_gesamt"], e["quellen"]), reverse=True)
    assigned = sum(1 for r in rows if r.get("thema_id"))
    return {
        "schema": SCHEMA,
        "stand": now.astimezone(BERLIN).isoformat(timespec="minutes"),
        "fenster_stunden": WINDOW_HOURS,
        "gruppen": {"lager": list(CAMPS), "spektrum": list(SPECTRA)},
        "artikel_je_gruppe": {"lager": dict(per_camp), "spektrum": dict(per_spectrum)},
        "artikel_gesamt": len(rows),
        "artikel_zugeordnet": assigned,
        "quellen_gesamt": len(media),
        "medien": sorted(media.values(), key=lambda m: m["name"]),
        "themen": entries[:MAX_TOPICS],
    }


def write_payload(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), "utf-8")
