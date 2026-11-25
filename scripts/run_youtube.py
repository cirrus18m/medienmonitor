"""YouTube-Trends: neue Videos der Kanäle aus youtube.yaml abrufen, filtern und
youtube.json, youtube.html (Grafik) und kanaele.html (Kanalübersicht) für
deutschlandmonitor.info schreiben.

Für „Aufrufe am ersten Tag“ merkt sich jeder Lauf die Aufrufe junger Videos in
--zwischenstand (Standard youtube-zwischenstand.json, nicht im Repo; im Workflow im
Actions-Cache). Einträge fallen nach 11 Tagen heraus.

    YOUTUBE_API_KEY=… uv run scripts/run_youtube.py --out ausgabe
    uv run scripts/run_youtube.py --beispiel --out ausgabe   # ohne API, erfundene Videos

Der Schlüssel kommt aus der Umgebung oder aus .env (Zeile YOUTUBE_API_KEY=…) und wird nie
ausgegeben.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from medienmonitor import youtube, youtube_render

ROOT = Path(__file__).resolve().parent.parent


def api_key() -> str:
    key = os.environ.get("YOUTUBE_API_KEY", "")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "YOUTUBE_API_KEY":
                key = value.strip().strip("\"'")
    return key


def example(channels: list[youtube.Channel], now: datetime):
    """Made-up videos to look at the chart without an API key."""
    rng = random.Random(1)
    videos = []
    for n, channel in enumerate(channels * 3):
        published = now - timedelta(hours=rng.uniform(1, 24 * 11))
        video = youtube.Video(
            video_id=f"beispiel{n:03d}",
            kanal=channel.name,
            titel=f"Beispielvideo {n} von {channel.name}",
            veroeffentlicht=published,
            dauer_s=rng.choice([300, 900, 2400, 5400]),
            aufrufe=int(10 ** rng.uniform(3, 6.3)),
            live=rng.random() < 0.1,
            sprache=channel.sprache if channel.sprache != "mehrsprachig" else "",
        )
        videos.append((video, channel))
    subscribers = {c.kanal_id: int(10 ** rng.uniform(4, 6.5)) for c in channels}
    return videos, [], subscribers


def example_snapshots(videos, now: datetime) -> dict:
    """Made-up counts around the first day for the example videos older than a day."""
    snapshots = {}
    for video, _ in videos:
        hours = (now - video.veroeffentlicht).total_seconds() / 3600
        if hours > 24:
            share = 0.3 + 0.4 * (sum(map(ord, video.video_id)) % 100) / 100
            snapshots[video.video_id] = {
                "veroeffentlicht": video.veroeffentlicht.isoformat(),
                "vor": [22.5, int(video.aufrufe * share * 0.95)],
                "nach": [25.5, int(video.aufrufe * share * 1.05)],
            }
    return snapshots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kanaele", type=Path, default=ROOT / "youtube.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "ausgabe")
    parser.add_argument("--beispiel", action="store_true", help="erfundene Videos, ohne API")
    parser.add_argument("--zwischenstand", type=Path, default=ROOT / "youtube-zwischenstand.json")
    args = parser.parse_args()
    now = datetime.now(UTC)
    channels = youtube.load_channels(args.kanaele)

    if args.beispiel:
        videos, errors, subscribers = example(channels, now)
        snapshots = example_snapshots(videos, now)
    else:
        try:
            api = youtube.YouTubeApi(api_key())
            videos, errors, subscribers = youtube.fetch(channels, api, now)
        except youtube.YouTubeError as exc:
            print(f"Abbruch: {exc}")
            return 1
        snapshots = {}
        if args.zwischenstand.exists():
            snapshots = json.loads(args.zwischenstand.read_text(encoding="utf-8"))
        snapshots = youtube.update_snapshots(snapshots, videos, now)
        args.zwischenstand.write_text(json.dumps(snapshots), encoding="utf-8")

    payload = youtube.build_payload(videos, now, errors, channels, subscribers, snapshots)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "youtube.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    youtube_render.write_html(payload, args.out)
    print(
        f"{len(channels)} Kanäle, {payload['videos_geprueft']} Videos geprüft, "
        f"{payload['videos_gezaehlt']} gezählt {payload['gezaehlt_je_liste']}, "
        f"ausgeschlossen: {payload['ausgeschlossen']}; "
        f"{payload['mit_erstem_tag']} mit Aufrufen am ersten Tag."
    )
    for line in errors:
        print(f"  Fehler – {line}")
    # fail only if (almost) every channel broke
    return 1 if len(errors) > len(channels) // 2 else 0


if __name__ == "__main__":
    sys.exit(main())
