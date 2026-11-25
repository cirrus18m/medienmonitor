"""Build daten.json for the page "Medienmonitor": topics of the last 24 hours by group.

Shares are per group: articles of the group on the topic / all articles of the group in
the window (in percent), so groups with many feeds do not dominate. The same holds per
medium ("medien", "anzahl_medium"): articles of the medium on the topic / all its articles.
Each medium also carries its home page (``domain`` from feeds.yaml) and its latest
headlines of the window (``neueste``, any topic). ``kategorien`` holds the TOP-Themen
and Blasen-Themen (see bubbles.py).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from medienmonitor import bubbles, store
from medienmonitor.topics import OTHER, TopicList

SCHEMA = 1
WINDOW_HOURS = 24
MIN_ARTICLES = 5
MIN_SOURCES = 2
MAX_TOPICS = 40
LATEST_PER_MEDIUM = 10
CAMPS = ("links", "mitte", "rechts", "alternativ")
SPECTRA = ("links", "mitte-links", "mitte", "mitte-rechts", "rechts", "unklar")
BERLIN = ZoneInfo("Europe/Berlin")


_time = store.row_time


def window_rows(
    data_dir: Path, now: datetime, hours: int = WINDOW_HOURS, start: datetime | None = None
) -> list[dict]:
    """Headlines of the last ``hours`` hours, or since ``start`` if given."""
    begin = start if start is not None else now - timedelta(hours=hours)
    limit = begin.astimezone(UTC).isoformat(timespec="seconds")
    days = (now - begin).days + 2
    return [row for row in store.read_days(data_dir, now.date(), days) if _time(row) >= limit]


def start_of_day(now: datetime) -> datetime:
    """Midnight of today in Berlin (filter "nur heute")."""
    local = now.astimezone(BERLIN)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _shares(counts: Counter, totals: Counter, keys: tuple[str, ...]) -> dict[str, float]:
    return {k: round(100 * counts[k] / totals[k], 1) if totals[k] else 0.0 for k in keys}


def _topic_name(topics: TopicList, topic_id: str | None) -> str | None:
    topic_id = topics.resolve(topic_id)
    if not topic_id or topic_id == OTHER or topic_id not in topics.themen:
        return None
    return topics.themen[topic_id]["name"]


def build_payload(
    data_dir: Path,
    now: datetime | None = None,
    domains: dict[str, str] | None = None,
    start: datetime | None = None,
    categories: bool = True,
) -> dict:
    """Topics of the last WINDOW_HOURS hours, or since ``start`` (filter "nur heute").

    ``domains``: medium name -> home page (feeds.yaml), shown as link in the chart.
    ``categories``: add the TOP- and Blasen-Themen (bubbles.py).
    """
    now = now or datetime.now(UTC)
    domains = domains or {}
    topics = TopicList.load(data_dir)
    rows = window_rows(data_dir, now, start=start)
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
                "domain": domains.get(row["quelle"]),
                "artikel": 0,
                "neueste": [],
            },
        )
        medium["artikel"] += 1
        medium["neueste"].append(row)
    for medium in media.values():
        latest = sorted(medium["neueste"], key=_time, reverse=True)[:LATEST_PER_MEDIUM]
        medium["neueste"] = [
            {
                "titel": r["titel"],
                "url": r["url"],
                "zeit": _time(r),
                "thema": _topic_name(topics, r.get("thema_id")),
            }
            for r in latest
        ]

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        topic_id = topics.resolve(row.get("thema_id"))
        if (
            topic_id
            and topic_id != OTHER
            and topic_id in topics.themen
            and not topics.themen[topic_id].get("aufgeloest")
        ):
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
        "fenster": "heute" if start is not None else "24h",
        "seit": (start or now - timedelta(hours=WINDOW_HOURS))
        .astimezone(BERLIN)
        .isoformat(timespec="minutes"),
        "gruppen": {"lager": list(CAMPS), "spektrum": list(SPECTRA)},
        "artikel_je_gruppe": {"lager": dict(per_camp), "spektrum": dict(per_spectrum)},
        "artikel_gesamt": len(rows),
        "artikel_zugeordnet": assigned,
        "quellen_gesamt": len(media),
        "medien": sorted(media.values(), key=lambda m: m["name"]),
        "themen": entries[:MAX_TOPICS],
        "kategorien": (
            bubbles.categories(window_rows(data_dir, now, bubbles.BUBBLE_HOURS), topics, now)
            if categories
            else None
        ),
    }


def write_payload(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), "utf-8")
