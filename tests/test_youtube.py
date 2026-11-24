import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from medienmonitor import youtube, youtube_render

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def channel(**extra):
    values = {
        "name": "Kanal A",
        "kanal_id": "UCabc",
        "land": "DE",
        "art": "unabhaengig",
        "lager": "alternativ",
        "spektrum": "rechts",
    }
    return youtube.Channel(**{**values, **extra})


def video(**extra):
    values = {
        "video_id": "v1",
        "kanal": "Kanal A",
        "titel": "Gespräch über die Rente",
        "veroeffentlicht": NOW - timedelta(days=2),
        "dauer_s": 3600,
        "aufrufe": 50_000,
        "live": False,
    }
    return youtube.Video(**{**values, **extra})


def test_parse_duration():
    assert youtube.parse_duration("PT1H2M3S") == 3723
    assert youtube.parse_duration("PT15M") == 900
    assert youtube.parse_duration("P1DT1S") == 86401
    assert youtube.parse_duration("P0D") == 0
    assert youtube.parse_duration("") == 0


def test_load_channels_only_active_with_id(tmp_path):
    path = tmp_path / "youtube.yaml"
    path.write_text(
        "kanaele:\n"
        "  - {name: A, kanal_id: UC1, land: DE, art: politik, lager: '', spektrum: rechts}\n"
        "  - {name: B, kanal_id: '', land: DE, art: x, lager: mitte, spektrum: mitte,"
        " aktiv: false}\n"
        "  - {name: C, kanal_id: UC3, land: DE, art: x, lager: mitte, spektrum: mitte,"
        " ausschliessen: ['^Kurz:']}\n",
        encoding="utf-8",
    )
    channels = youtube.load_channels(path)
    assert [c.name for c in channels] == ["A", "C"]
    assert channels[1].ausschliessen == ("^Kurz:",)
    assert channels[0].uploads_playlist == "UU1"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({}, None),
        ({"dauer_s": 600}, "kurz"),
        ({"live": True}, "live"),
        ({"veroeffentlicht": NOW - timedelta(days=11)}, "älter"),
        ({"aufrufe": None}, "ohne Aufrufe"),
        ({"titel": "tagesschau 20:00 Uhr, 23.11.2026"}, "Nachrichten"),
        ({"titel": "Kurz: Neues"}, "Nachrichten"),
        ({"titel": "heute 19 Uhr vom 23.11.2026: Polen"}, "Nachrichten"),
        ({"titel": "Bundestag, 110. Sitzung: Etat | 24.11.26"}, "Nachrichten"),
        ({"titel": "18. November 2026 - Regierungspressekonferenz | Komplette BPK"}, "Nachrichten"),
    ],
)
def test_exclusion_reason(changes, reason):
    assert youtube.exclusion_reason(video(**changes), channel(ausschliessen=("^Kurz:",)), NOW) == (
        reason
    )


def test_video_from_api_marks_recorded_livestreams():
    item = {
        "id": "x",
        "snippet": {
            "title": "T",
            "publishedAt": "2026-11-23T10:00:00Z",
            "liveBroadcastContent": "none",
        },
        "contentDetails": {"duration": "PT1H"},
        "statistics": {"viewCount": "123"},
        "liveStreamingDetails": {"actualStartTime": "2026-11-23T10:00:00Z"},
    }
    parsed = youtube.Video.from_api(item, channel())
    assert parsed.live and parsed.dauer_s == 3600 and parsed.aufrufe == 123


def test_build_payload_top_and_per_day():
    videos = [(video(video_id=f"v{n}", aufrufe=1000 * n), channel()) for n in range(1, 40)] + [
        (video(video_id="kurz", dauer_s=60, aufrufe=10**9), channel())
    ]
    payload = youtube.build_payload(videos, NOW)
    assert len(payload["videos"]) == youtube.TOP_N
    assert payload["videos"][0]["video_id"] == "v39"
    assert payload["videos"][0]["aufrufe_je_tag"] == 19_500  # 39.000 in 2 days
    assert payload["ausgeschlossen"] == {"kurz": 1}
    assert payload["videos_gezaehlt"] == 39


def fake_api(handler):
    return youtube.YouTubeApi("GEHEIM", httpx.Client(transport=httpx.MockTransport(handler)))


def test_fetch_stops_at_older_uploads_and_hides_key():
    def handler(request):
        params = request.url.params
        assert params["key"] == "GEHEIM"
        if request.url.path.endswith("playlistItems"):
            if params["playlistId"] == "UUkaputt":
                error = {"error": {"errors": [{"reason": "quotaExceeded"}]}}
                return httpx.Response(403, json=error)
            items = [
                {"contentDetails": {"videoId": "neu", "videoPublishedAt": "2026-11-23T00:00:00Z"}},
                {"contentDetails": {"videoId": "alt", "videoPublishedAt": "2026-10-01T00:00:00Z"}},
            ]
            return httpx.Response(200, json={"items": items, "nextPageToken": "weiter"})
        assert params["id"] == "neu"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "neu",
                        "snippet": {"title": "T", "publishedAt": "2026-11-23T00:00:00Z"},
                        "contentDetails": {"duration": "PT20M"},
                        "statistics": {"viewCount": "5"},
                    }
                ]
            },
        )

    channels = [channel(), channel(name="Kaputt", kanal_id="UCkaputt")]
    videos, errors = youtube.fetch(channels, fake_api(handler), NOW)
    assert [v.video_id for v, _ in videos] == ["neu"]
    assert errors == ["Kaputt: playlistItems: HTTP 403 (quotaExceeded)"]
    assert "GEHEIM" not in " ".join(errors)


def test_api_needs_key():
    with pytest.raises(youtube.YouTubeError):
        youtube.YouTubeApi("")


def test_render_escapes_titles_and_groups():
    videos = [
        (video(titel="</script><script>alert(1)</script> lang genug"), channel()),
        (video(video_id="p", aufrufe=10), channel(name="Partei", art="politik", lager="")),
    ]
    html = youtube_render.render_html(youtube.build_payload(videos, NOW))
    assert "<script>alert(1)" not in html
    data = json.loads(html.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    assert [row[1] for row in data["rows"]] == ["neu", "politik"]
    assert {t["meta"]["gruppe"] for t in data["figure"]["data"]} == {"neu", "politik"}
    assert data["figure"]["layout"]["yaxis"]["type"] == "log"
