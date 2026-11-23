"""Feed list and headline parsing. Network access only in ``fetch_feed``."""

from __future__ import annotations

import calendar
import hashlib
import html
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
import yaml

USER_AGENT = "Mozilla/5.0 (compatible; medienmonitor/0.1; RSS reader)"
TIMEOUT_S = 20.0

# Query parameters that only track the reader; dropped so the same article dedupes.
TRACKING_PARAMS = re.compile(r"^(utm_.*|wt_.*|ref|cid|xtor|at_.*|fbclid|gclid|dicbo)$", re.I)


@dataclass(frozen=True)
class Feed:
    """One entry of feeds.yaml (field names as in the file)."""

    name: str
    domain: str
    land: str
    feed: str
    lager: str
    spektrum: str
    pruefen: bool = False
    aktiv: bool = True


@dataclass
class Headline:
    """One stored headline. Keys are the field names of the JSONL files."""

    id: str
    quelle: str
    lager: str
    spektrum: str
    land: str
    titel: str
    url: str
    veroeffentlicht: str | None  # ISO 8601 UTC, None if the feed has no date
    abgerufen: str  # ISO 8601 UTC
    thema_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def load_feeds(path: Path, only_active: bool = True) -> list[Feed]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    feed_list = [Feed(**entry) for entry in data["quellen"]]
    return [f for f in feed_list if f.aktiv or not only_active]


def normalize_url(url: str) -> str:
    """Lower-case scheme/host, drop fragment, tracking parameters and trailing slash."""
    parts = urlsplit(url.strip())
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not TRACKING_PARAMS.match(k)
        ]
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def headline_id(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode()).hexdigest()[:16]


def clean_title(raw: str) -> str:
    text = re.sub(r"<[^>]+>", "", html.unescape(raw or ""))
    return re.sub(r"\s+", " ", text).strip()


def _entry_time(entry) -> str | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), UTC).isoformat(timespec="seconds")
    return None


def parse_feed(content: bytes, feed: Feed, fetched: datetime) -> list[Headline]:
    """Feed bytes -> headlines; entries without title or link are skipped."""
    parsed = feedparser.parse(content)
    fetched_iso = fetched.astimezone(UTC).isoformat(timespec="seconds")
    headlines: dict[str, Headline] = {}
    for entry in parsed.entries:
        title = clean_title(entry.get("title", ""))
        link = (entry.get("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        hid = headline_id(link)
        headlines[hid] = Headline(
            id=hid,
            quelle=feed.name,
            lager=feed.lager,
            spektrum=feed.spektrum,
            land=feed.land,
            titel=title,
            url=link,
            veroeffentlicht=_entry_time(entry),
            abgerufen=fetched_iso,
        )
    return list(headlines.values())


def fetch_feed(feed: Feed, client: httpx.Client) -> bytes:
    response = client.get(feed.feed)
    response.raise_for_status()
    return response.content


def http_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S, follow_redirects=True
    )
