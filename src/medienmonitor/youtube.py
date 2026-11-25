"""YouTube trends: the most watched long videos (interviews, documentaries) of the channels
in youtube.yaml during the last days.

Uses the YouTube Data API v3 with an API key (``YOUTUBE_API_KEY``). Per run and channel one
``playlistItems.list`` call on the uploads playlist (1 unit per page), then ``videos.list``
for up to 50 videos per call (1 unit). Network access only in ``YouTubeApi``; everything
else is pure and testable.

Only titles, channel, figures and links are kept, and only in the current ``youtube.json``
(no history: the API terms limit how long API data may be stored without refreshing it).
Two short-lived stores exist outside the repository (Actions cache in the workflow): the
views of young videos (``update_snapshots``, WINDOW_DAYS + 1 days) and one subscriber
count per channel and day (``update_subscriber_history``, SUBSCRIBER_DAYS days). GitHub
deletes caches that were not used for 7 days, so no value is older than 30 days.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import yaml

API = "https://www.googleapis.com/youtube/v3"
TIMEOUT_S = 20.0
WINDOW_DAYS = 10
TOP_N = 50
MAX_PER_CHANNEL = 3  # per list, so that a few busy channels do not fill it
MIN_DURATION_S = 8 * 60  # interviews, talks and documentaries, no news clips or Shorts
SCHEMA = 3
LANGUAGES = ("de", "en")  # choices of the chart; "alle" = both
LISTS = ("de", "en", "alle")
# sort keys of the lists (fields of a list entry)
METRICS = ("aufrufe", "aufrufe_je_tag", "aufrufe_erster_tag")
FIRST_DAY_H = 24
MAX_GAP_H = 12  # snapshots around 24 h further apart give no first-day value
# Subscriber history: one count per channel and day. 21 days plus at most 7 days in an
# unused Actions cache stays below the 30 days of the YouTube API terms.
SUBSCRIBER_DAYS = 21

# Titles of regular news programs and live broadcasts (all channels); per channel more
# patterns in youtube.yaml (field "ausschliessen").
DEFAULT_EXCLUDE = (
    r"\blive\b",
    r"\blivestream\b",
    r"pressekonferenz",
    r"bundestag, \d+\. sitzung",
    r"tagesschau \d{1,2}[:.]\d{2}",
    r"tagesthemen \d{1,2}[:.]\d{2}",
    r"heute journal",
    r"heute \d{1,2}([:.]\d{2})? uhr vom",
    r"nachrichten (am|vom|des tages)",
    r"schlagzeilen des tages",
    r"news am",
)

_DURATION = re.compile(r"^P(?:(?P<d>\d+)D)?(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?)?$")


class YouTubeError(RuntimeError):
    """API not reachable, key missing or invalid."""


@dataclass(frozen=True)
class Channel:
    """One entry of youtube.yaml (field names as in the file)."""

    name: str
    kanal_id: str
    land: str
    art: str
    lager: str
    spektrum: str
    handle: str = ""
    sprache: str = "de"  # de | en | mehrsprachig
    aktiv: bool = True
    ausschliessen: tuple[str, ...] = field(default_factory=tuple)

    @property
    def uploads_playlist(self) -> str:
        """Playlist of all uploads: channel id with UU instead of UC."""
        return "UU" + self.kanal_id[2:]

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/channel/{self.kanal_id}"


def load_channels(path: Path) -> list[Channel]:
    """Active channels with an id."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    channels = []
    for entry in data.get("kanaele", []):
        entry = {k: v for k, v in entry.items() if k in Channel.__dataclass_fields__}
        entry["ausschliessen"] = tuple(entry.get("ausschliessen") or ())
        entry["lager"] = entry.get("lager") or ""
        # YAML reads some codes as other types (land: NO -> False)
        for key in ("land", "sprache", "art", "spektrum"):
            if key in entry and not isinstance(entry[key], str):
                raise ValueError(f"{entry['name']}: {key} in Anführungszeichen setzen")
        channel = Channel(**entry)
        if channel.aktiv and channel.kanal_id.startswith("UC"):
            channels.append(channel)
    return channels


def parse_duration(text: str) -> int:
    """ISO 8601 duration of the API (``PT1H2M3S``) in seconds; 0 if unknown."""
    match = _DURATION.match(text or "")
    if not match:
        return 0
    d, h, m, s = (int(match.group(k) or 0) for k in "dhms")
    return ((d * 24 + h) * 60 + m) * 60 + s


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


@dataclass
class Video:
    video_id: str
    kanal: str
    titel: str
    veroeffentlicht: datetime
    dauer_s: int
    aufrufe: int | None
    live: bool
    sprache: str = ""  # audio (or metadata) language of the video, if the channel sets it

    @classmethod
    def from_api(cls, item: dict, channel: Channel) -> Video:
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        views = stats.get("viewCount")
        return cls(
            video_id=item["id"],
            kanal=channel.name,
            titel=snippet.get("title", ""),
            veroeffentlicht=parse_time(snippet["publishedAt"]),
            dauer_s=parse_duration(item.get("contentDetails", {}).get("duration", "")),
            aufrufe=int(views) if views is not None else None,
            live="liveStreamingDetails" in item
            or snippet.get("liveBroadcastContent", "none") != "none",
            sprache=snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage") or "",
        )


def video_language(video: Video, channel: Channel) -> str | None:
    """Language of a video: that of the channel; for multilingual channels as set for the
    video (None if not set). Channels often set a wrong video language (German video
    marked "en"), so it is used only where the channel has no single language."""
    if channel.sprache in LANGUAGES:
        return channel.sprache
    return video.sprache.split("-")[0].lower() or None


def in_list(language: str | None, key: str) -> bool:
    """Whether a video of this language belongs to list "de", "en" or "alle" (both;
    unknown language of a multilingual channel only there)."""
    if key == "alle":
        return language in LANGUAGES or language is None
    return language == key


def exclusion_reason(video: Video, channel: Channel, now: datetime) -> str | None:
    """Why a video does not count, or None if it does."""
    if now - video.veroeffentlicht > timedelta(days=WINDOW_DAYS):
        return "älter"
    if video.live:
        return "live"
    if video.dauer_s <= MIN_DURATION_S:
        return "kurz"
    if video.aufrufe is None:
        return "ohne Aufrufe"
    for pattern in DEFAULT_EXCLUDE + channel.ausschliessen:
        if re.search(pattern, video.titel, re.IGNORECASE):
            return "Nachrichten"
    return None


def update_snapshots(snapshots: dict, videos: list[tuple[Video, Channel]], now: datetime) -> dict:
    """Remember the views of counting videos shortly before and after their first day.

    YouTube only reports the current view count. Runs every 3 hours keep per video the last
    count before 24 hours online ("vor") and the first one after ("nach", [hours, views]);
    ``first_day_views`` interpolates between them. Entries leave after WINDOW_DAYS + 1 days,
    so nothing is kept longer than the API terms allow (30 days).
    """
    limit = now - timedelta(days=WINDOW_DAYS + 1)
    kept = {
        video_id: entry
        for video_id, entry in snapshots.items()
        if parse_time(entry["veroeffentlicht"]) > limit
    }
    for video, channel in videos:
        if exclusion_reason(video, channel, now):
            continue
        hours = round((now - video.veroeffentlicht).total_seconds() / 3600, 2)
        entry = kept.setdefault(
            video.video_id,
            {"veroeffentlicht": video.veroeffentlicht.isoformat(), "vor": None, "nach": None},
        )
        if hours < FIRST_DAY_H:
            entry["vor"] = [hours, video.aufrufe]
        elif entry["nach"] is None:
            entry["nach"] = [hours, video.aufrufe]
    return kept


def update_subscriber_history(
    history: dict, subscribers: dict[str, int | None], now: datetime
) -> dict:
    """Channel id -> {date: subscribers}; today's count replaces an earlier one of the
    day, counts older than SUBSCRIBER_DAYS days leave."""
    today = now.date()
    oldest = (today - timedelta(days=SUBSCRIBER_DAYS)).isoformat()
    kept = {
        channel_id: {day: count for day, count in days.items() if day > oldest}
        for channel_id, days in history.items()
    }
    for channel_id, count in subscribers.items():
        if count is not None:
            kept.setdefault(channel_id, {})[today.isoformat()] = count
    return {channel_id: days for channel_id, days in kept.items() if days}


def subscriber_change(days: dict[str, int] | None, now: datetime) -> dict:
    """Change from the oldest stored count (before today) to the newest one:
    ``{"seit": date, "absolut": int, "relativ_pct": float}`` or empty values."""
    empty = {"seit": None, "absolut": None, "relativ_pct": None}
    if not days:
        return empty
    today = now.date().isoformat()
    earlier = sorted(day for day in days if day < today)
    if not earlier:
        return empty
    first, last = days[earlier[0]], days[max(days)]
    return {
        "seit": earlier[0],
        "absolut": last - first,
        "relativ_pct": round(100 * (last - first) / first, 2) if first else None,
    }


def first_day_views(entry: dict | None) -> int | None:
    """Views after 24 hours, linear between the counts before and after; None if unknown
    (video first seen after its first day, or the counts are too far apart)."""
    if not entry or not entry.get("vor") or not entry.get("nach"):
        return None
    (h1, v1), (h2, v2) = entry["vor"], entry["nach"]
    if h2 - h1 > MAX_GAP_H or h2 <= h1:
        return None
    return round(v1 + (v2 - v1) * (FIRST_DAY_H - h1) / (h2 - h1))


class YouTubeApi:
    """The two API calls needed; ``key`` is never logged."""

    def __init__(self, key: str, client: httpx.Client | None = None):
        if not key:
            raise YouTubeError("YOUTUBE_API_KEY fehlt.")
        self._key = key
        self._client = client or httpx.Client(timeout=TIMEOUT_S)

    def redact(self, text: str) -> str:
        """Message without the key (httpx errors may contain the URL)."""
        return text.replace(self._key, "***")

    def _get(self, path: str, **params) -> dict:
        response = self._client.get(f"{API}/{path}", params={**params, "key": self._key})
        if response.status_code != 200:
            try:
                reason = response.json()["error"]["errors"][0]["reason"]
            except (ValueError, KeyError, IndexError):
                reason = "unbekannt"
            # no URL in the message: it contains the key
            raise YouTubeError(f"{path}: HTTP {response.status_code} ({reason})")
        return response.json()

    def recent_ids(self, channel: Channel, since: datetime, max_pages: int = 5) -> list[str]:
        """Ids of the uploads published after ``since`` (newest first)."""
        ids: list[str] = []
        token = None
        for _ in range(max_pages):
            params = {"part": "contentDetails", "playlistId": channel.uploads_playlist}
            params["maxResults"] = 50
            if token:
                params["pageToken"] = token
            page = self._get("playlistItems", **params)
            older = False
            for item in page.get("items", []):
                details = item.get("contentDetails", {})
                published = details.get("videoPublishedAt")
                if published and parse_time(published) < since:
                    older = True
                    continue
                ids.append(details["videoId"])
            token = page.get("nextPageToken")
            if older or not token:
                break
        return ids

    def subscribers(self, channel_ids: Iterable[str]) -> dict[str, int | None]:
        """Channel id -> number of subscribers (None if the channel hides it). The API
        rounds large numbers to three significant digits."""
        ids = list(dict.fromkeys(channel_ids))
        result: dict[str, int | None] = {}
        for start in range(0, len(ids), 50):
            page = self._get(
                "channels", part="statistics", id=",".join(ids[start : start + 50]), maxResults=50
            )
            for item in page.get("items", []):
                stats = item.get("statistics", {})
                hidden = stats.get("hiddenSubscriberCount") or "subscriberCount" not in stats
                result[item["id"]] = None if hidden else int(stats["subscriberCount"])
        return result

    def videos(self, ids: Iterable[str]) -> list[dict]:
        ids = list(dict.fromkeys(ids))
        items: list[dict] = []
        for start in range(0, len(ids), 50):
            page = self._get(
                "videos",
                part="snippet,contentDetails,statistics,liveStreamingDetails",
                id=",".join(ids[start : start + 50]),
                maxResults=50,
            )
            items.extend(page.get("items", []))
        return items


def _entry(
    video: Video, channel: Channel, language, subscribers, now: datetime, first_day=None
) -> dict:
    days = max((now - video.veroeffentlicht).total_seconds() / 86400, 1 / 24)
    return {
        "video_id": video.video_id,
        "titel": video.titel,
        "kanal": channel.name,
        "kanal_url": channel.url,
        "abonnenten": subscribers.get(channel.kanal_id),
        "sprache": language or "",
        "art": channel.art,
        "lager": channel.lager,
        "spektrum": channel.spektrum,
        "veroeffentlicht": video.veroeffentlicht.isoformat(),
        "tage_online": round(days, 2),
        "dauer_s": video.dauer_s,
        "aufrufe": video.aufrufe,
        "aufrufe_je_tag": round(video.aufrufe / days),
        "aufrufe_erster_tag": first_day,
        "url": f"https://www.youtube.com/watch?v={video.video_id}",
    }


def build_payload(
    videos: list[tuple[Video, Channel]],
    now: datetime,
    errors: list[str] | None = None,
    channels: list[Channel] | None = None,
    subscribers: dict[str, int | None] | None = None,
    snapshots: dict | None = None,
    subscriber_history: dict | None = None,
) -> dict:
    """youtube.json: per language choice and per metric (METRICS) the TOP_N counting
    videos of the last WINDOW_DAYS (at most MAX_PER_CHANNEL per channel), and the list of
    channels. ``snapshots`` (update_snapshots) give the views on the first day,
    ``subscriber_history`` (update_subscriber_history) the change of subscribers."""
    subscribers = subscribers or {}
    snapshots = snapshots or {}
    subscriber_history = subscriber_history or {}
    channels = channels if channels is not None else list({c.name: c for _, c in videos}.values())
    counting = []
    reasons: dict[str, int] = {}
    per_channel: dict[str, list[int]] = {}
    for video, channel in videos:
        reason = exclusion_reason(video, channel, now)
        seen = per_channel.setdefault(channel.name, [0, 0])
        if reason != "älter":
            seen[0] += 1
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            seen[1] += 1
            counting.append((video, channel, video_language(video, channel)))
    entries = [
        (
            _entry(
                video,
                channel,
                language,
                subscribers,
                now,
                first_day_views(snapshots.get(video.video_id)),
            ),
            language,
        )
        for video, channel, language in counting
    ]
    lists = {}
    for key in LISTS:
        lists[key] = {}
        for metric in METRICS:
            ranked = sorted(
                (item for item in entries if item[0][metric] is not None),
                key=lambda item: item[0][metric],
                reverse=True,
            )
            chosen, per_list = [], {}
            for entry, language in ranked:
                name = entry["kanal"]
                if in_list(language, key) and per_list.get(name, 0) < MAX_PER_CHANNEL:
                    per_list[name] = per_list.get(name, 0) + 1
                    chosen.append(entry)
                if len(chosen) == TOP_N:
                    break
            lists[key][metric] = [
                {"rang": rank, **entry} for rank, entry in enumerate(chosen, start=1)
            ]
    return {
        "schema": SCHEMA,
        "stand": now.isoformat(timespec="minutes"),
        "fenster_tage": WINDOW_DAYS,
        "mindestdauer_min": MIN_DURATION_S // 60,
        "abo_tage": SUBSCRIBER_DAYS,
        "videos_geprueft": len(videos),
        "videos_gezaehlt": len(counting),
        "gezaehlt_je_liste": {key: sum(in_list(i[2], key) for i in counting) for key in LISTS},
        "mit_erstem_tag": sum(e["aufrufe_erster_tag"] is not None for e, _ in entries),
        "ausgeschlossen": dict(sorted(reasons.items())),
        "fehler": errors or [],
        "listen": lists,
        "kanaele": [
            {
                "name": c.name,
                "url": c.url,
                "handle": c.handle,
                "sprache": c.sprache,
                "land": c.land,
                "art": c.art,
                "lager": c.lager,
                "spektrum": c.spektrum,
                "abonnenten": subscribers.get(c.kanal_id),
                "abo_veraenderung": subscriber_change(subscriber_history.get(c.kanal_id), now),
                "videos": per_channel.get(c.name, [0, 0])[0],
                "gezaehlt": per_channel.get(c.name, [0, 0])[1],
            }
            for c in sorted(channels, key=lambda c: c.name.casefold())
        ],
    }


def fetch(channels: list[Channel], api: YouTubeApi, now: datetime):
    """All recent videos of the channels, errors per channel as German messages and the
    subscribers per channel id."""
    since = now - timedelta(days=WINDOW_DAYS)
    by_id: dict[str, Channel] = {}
    errors: list[str] = []
    for channel in channels:
        try:
            for video_id in api.recent_ids(channel, since):
                by_id[video_id] = channel
        except (YouTubeError, httpx.HTTPError) as exc:
            errors.append(api.redact(f"{channel.name}: {exc}"))
    videos = [
        (Video.from_api(item, by_id[item["id"]]), by_id[item["id"]])
        for item in api.videos(by_id)
        if item.get("id") in by_id
    ]
    try:
        subscribers = api.subscribers(c.kanal_id for c in channels)
    except (YouTubeError, httpx.HTTPError) as exc:
        errors.append(api.redact(f"Abonnenten: {exc}"))
        subscribers = {}
    return videos, errors, subscribers
