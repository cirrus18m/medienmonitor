"""Headline store: one JSONL file per day (UTC) under <data_dir>/titel/JJJJ/MM/TT.jsonl."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from medienmonitor.feeds import Headline

TITLES_DIR = "titel"


def row_time(row: dict) -> str:
    """Publication time if known and not in the future, else time of fetching."""
    published = row.get("veroeffentlicht")
    if published and published <= row["abgerufen"]:
        return published
    return row["abgerufen"]


def day_file(data_dir: Path, day: date) -> Path:
    return data_dir / TITLES_DIR / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.jsonl"


def read_day(data_dir: Path, day: date) -> list[dict]:
    path = day_file(data_dir, day)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def read_days(data_dir: Path, end: date, days: int) -> Iterator[dict]:
    for offset in range(days - 1, -1, -1):
        yield from read_day(data_dir, end - timedelta(days=offset))


def write_day(data_dir: Path, day: date, rows: list[dict]) -> None:
    path = day_file(data_dir, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def set_topics(
    data_dir: Path, end: date, days: int, topic_of: dict[str, str], field: str = "thema_id"
) -> int:
    """Write ``field`` (``thema_id`` or ``thema_neu_id``) for the given headline ids into the
    day files; returns the count."""
    changed = 0
    for offset in range(days):
        day = end - timedelta(days=offset)
        rows = read_day(data_dir, day)
        dirty = False
        for row in rows:
            topic = topic_of.get(row["id"])
            if topic and row.get(field) != topic:
                row[field] = topic
                dirty = True
                changed += 1
        if dirty:
            write_day(data_dir, day, rows)
    return changed


def known_ids(data_dir: Path, today: date, days: int = 3) -> set[str]:
    """Ids seen in the last ``days`` days; feeds rarely keep entries longer."""
    return {row["id"] for row in read_days(data_dir, today, days)}


def append_new(
    data_dir: Path, headlines: Iterable[Headline], now: datetime | None = None
) -> list[Headline]:
    """Append headlines not seen before to today's file; returns the new ones."""
    now = now or datetime.now(UTC)
    today = now.astimezone(UTC).date()
    seen = known_ids(data_dir, today)
    new: list[Headline] = []
    for headline in headlines:
        if headline.id in seen:
            continue
        seen.add(headline.id)
        new.append(headline)
    if new:
        path = day_file(data_dir, today)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for headline in new:
                f.write(json.dumps(headline.to_dict(), ensure_ascii=False) + "\n")
    return new
