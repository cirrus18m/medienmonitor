"""YouTube trends: the most watched long videos (interviews, documentaries) of the channels
in youtube.yaml during the last days.

Uses the YouTube Data API v3 with an API key (``YOUTUBE_API_KEY``). Per run and channel one
``playlistItems.list`` call on the uploads playlist (1 unit per page), then ``videos.list``
for up to 50 videos per call (1 unit). Network access only in ``YouTubeApi``; everything
else is pure and testable.

Only titles, channel, figures and links are kept, and only in the current ``youtube.json``
(no history: the API terms limit how long API data may be stored without refreshing it).
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
TOP_N = 30
MIN_DURATION_S = 10 * 60  # interviews and documentaries, no news clips or Shorts
SCHEMA = 1

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
    aktiv: bool = True
    ausschliessen: tuple[str, ...] = field(default_factory=tuple)

    @property
    def uploads_playlist(self) -> str:
        """Playlist of all uploads: channel id with UU instead of UC."""
        return "UU" + self.kanal_id[2:]


def load_channels(path: Path) -> list[Channel]:
    """Active channels with an id."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    channels = []
    for entry in data.get("kanaele", []):
        entry = {k: v for k, v in entry.items() if k in Channel.__dataclass_fields__}
        entry["ausschliessen"] = tuple(entry.get("ausschliessen") or ())
        entry["lager"] = entry.get("lager") or ""
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
        )


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

    def recent_ids(self, channel: Channel, since: datetime, max_pages: int = 3) -> list[str]:
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


def build_payload(
    videos: list[tuple[Video, Channel]], now: datetime, errors: list[str] | None = None
) -> dict:
    """youtube.json: the TOP_N most watched counting videos of the last WINDOW_DAYS."""
    counting = []
    reasons: dict[str, int] = {}
    for video, channel in videos:
        reason = exclusion_reason(video, channel, now)
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            counting.append((video, channel))
    counting.sort(key=lambda pair: pair[0].aufrufe or 0, reverse=True)
    top = []
    for rank, (video, channel) in enumerate(counting[:TOP_N], start=1):
        days = max((now - video.veroeffentlicht).total_seconds() / 86400, 1 / 24)
        top.append(
            {
                "rang": rank,
                "video_id": video.video_id,
                "titel": video.titel,
                "kanal": channel.name,
                "art": channel.art,
                "lager": channel.lager,
                "spektrum": channel.spektrum,
                "veroeffentlicht": video.veroeffentlicht.isoformat(),
                "tage_online": round(days, 2),
                "dauer_s": video.dauer_s,
                "aufrufe": video.aufrufe,
                "aufrufe_je_tag": round(video.aufrufe / days),
                "url": f"https://www.youtube.com/watch?v={video.video_id}",
            }
        )
    return {
        "schema": SCHEMA,
        "stand": now.isoformat(timespec="minutes"),
        "fenster_tage": WINDOW_DAYS,
        "mindestdauer_min": MIN_DURATION_S // 60,
        "kanaele": len({channel.name for _, channel in videos}),
        "videos_geprueft": len(videos),
        "videos_gezaehlt": len(counting),
        "ausgeschlossen": dict(sorted(reasons.items())),
        "fehler": errors or [],
        "videos": top,
    }


def fetch(channels: list[Channel], api: YouTubeApi, now: datetime):
    """All recent videos of the channels; errors per channel as German messages."""
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
    return videos, errors
