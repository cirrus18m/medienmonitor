import json
from collections import Counter
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
        ({"dauer_s": 480}, "kurz"),
        ({"dauer_s": 481}, None),
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
    channels = [channel(name=f"K{n % 20:02d}") for n in range(80)]
    videos = [(video(video_id=f"v{n}", aufrufe=1000 * n), channels[n]) for n in range(1, 80)]
    videos.append((video(video_id="kurz", dauer_s=60, aufrufe=10**9), channels[0]))
    payload = youtube.build_payload(videos, NOW)
    top = payload["listen"]["de"]["aufrufe"]
    assert len(top) == youtube.TOP_N
    assert top[0]["video_id"] == "v79"
    assert top[0]["aufrufe_je_tag"] == 39_500  # 79.000 in 2 days
    assert payload["listen"]["en"] == {metric: [] for metric in youtube.METRICS}
    assert max(Counter(v["kanal"] for v in top).values()) == youtube.MAX_PER_CHANNEL
    first = payload["kanaele"][0]  # K00: v20, v40, v60 and the short video
    assert (first["name"], first["videos"], first["gezaehlt"]) == ("K00", 4, 3)
    assert payload["ausgeschlossen"] == {"kurz": 1}
    assert payload["videos_gezaehlt"] == 79
    assert payload["listen"]["de"]["aufrufe_erster_tag"] == []  # no snapshots


def test_lists_per_metric():
    young = video(video_id="jung", aufrufe=40_000, veroeffentlicht=NOW - timedelta(hours=12))
    old = video(video_id="alt", aufrufe=100_000, veroeffentlicht=NOW - timedelta(days=5))
    first = video(video_id="erster", aufrufe=60_000)  # 2 days online
    videos = [(young, channel(name="A")), (old, channel(name="B")), (first, channel(name="C"))]
    snapshots = {"erster": {"veroeffentlicht": "x", "vor": [22, 30_000], "nach": [25, 33_000]}}
    lists = youtube.build_payload(videos, NOW, snapshots=snapshots)["listen"]["de"]
    order = {metric: [v["video_id"] for v in lists[metric]] for metric in youtube.METRICS}
    assert order == {
        "aufrufe": ["alt", "erster", "jung"],
        "aufrufe_je_tag": ["jung", "erster", "alt"],  # 80.000, 30.000, 20.000 per day
        "aufrufe_erster_tag": ["erster"],
    }
    assert lists["aufrufe_erster_tag"][0]["aufrufe_erster_tag"] == 32_000


def test_snapshots_before_and_after_first_day():
    c = channel()
    published = NOW - timedelta(hours=21)
    snapshots = youtube.update_snapshots({}, [(video(veroeffentlicht=published), c)], NOW)
    assert snapshots["v1"]["vor"] == [21.0, 50_000] and snapshots["v1"]["nach"] is None
    assert youtube.first_day_views(snapshots["v1"]) is None
    later = NOW + timedelta(hours=6)  # 27 hours online
    snapshots = youtube.update_snapshots(
        snapshots, [(video(veroeffentlicht=published, aufrufe=56_000), c)], later
    )
    assert snapshots["v1"]["nach"] == [27.0, 56_000]
    assert youtube.first_day_views(snapshots["v1"]) == 53_000
    # the value after the first day stays; excluded videos are not kept
    snapshots = youtube.update_snapshots(
        snapshots,
        [
            (video(veroeffentlicht=published, aufrufe=90_000), c),
            (video(video_id="kurz", dauer_s=60, veroeffentlicht=published), c),
        ],
        later + timedelta(hours=3),
    )
    assert snapshots["v1"]["nach"] == [27.0, 56_000] and "kurz" not in snapshots
    # after WINDOW_DAYS + 1 days the entry leaves
    gone = NOW + timedelta(days=youtube.WINDOW_DAYS + 1)
    assert youtube.update_snapshots(snapshots, [], gone) == {}


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (None, None),
        ({"vor": None, "nach": [30, 100]}, None),  # first seen after its first day
        ({"vor": [6, 10], "nach": [30, 100]}, None),  # counts too far apart
        ({"vor": [23, 100], "nach": [25, 200]}, 150),
    ],
)
def test_first_day_views(entry, expected):
    assert youtube.first_day_views(entry) == expected


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
        if request.url.path.endswith("channels"):
            assert params["id"] == "UCabc,UCkaputt"
            items = [
                {"id": "UCabc", "statistics": {"subscriberCount": "1200"}},
                {"id": "UCkaputt", "statistics": {"hiddenSubscriberCount": True}},
            ]
            return httpx.Response(200, json={"items": items})
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
    videos, errors, subscribers = youtube.fetch(channels, fake_api(handler), NOW)
    assert [v.video_id for v, _ in videos] == ["neu"]
    assert errors == ["Kaputt: playlistItems: HTTP 403 (quotaExceeded)"]
    assert subscribers == {"UCabc": 1200, "UCkaputt": None}
    assert "GEHEIM" not in " ".join(errors)


def test_api_needs_key():
    with pytest.raises(youtube.YouTubeError):
        youtube.YouTubeApi("")


def test_languages_per_list():
    de, en = channel(), channel(name="B", sprache="en")
    multi = channel(name="C", sprache="mehrsprachig")
    videos = [
        (video(video_id="de"), de),
        (video(video_id="en"), en),
        (video(video_id="de-falsch", sprache="en"), de),  # channel language wins
        (video(video_id="en-video", sprache="en-US"), multi),
        (video(video_id="unbekannt"), multi),
        (video(video_id="tr", sprache="tr"), multi),
    ]
    lists = youtube.build_payload(videos, NOW)["listen"]
    ids = {key: sorted(v["video_id"] for v in lists[key]["aufrufe"]) for key in lists}
    assert ids == {
        "de": ["de", "de-falsch"],
        "en": ["en", "en-video"],
        "alle": ["de", "de-falsch", "en", "en-video", "unbekannt"],
    }


def test_render_escapes_titles_and_groups(tmp_path):
    videos = [
        (video(titel="</script><script>alert(1)</script> lang genug"), channel()),
        (
            video(video_id="m", aufrufe=10),
            channel(name="<b>Mitte</b>", art="oeffentlich", lager="mitte"),
        ),
    ]
    payload = youtube.build_payload(videos, NOW, subscribers={"UCabc": 2_140_000})
    html = youtube_render.render_html(payload)
    assert "<script>alert(1)" not in html
    data = json.loads(html.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    rows = data["views"]["de"]["aufrufe"]["rows"]
    assert [row[1] for row in rows] == ["unabhaengig", "medienhaus"]
    assert rows[0][9] == "2,14 Mio." and rows[0][11] == "–"  # no first-day value
    assert data["metrics"] == list(youtube.METRICS)
    for metric, label, _, _ in youtube_render.METRICS:
        figure = data["views"]["de"][metric]["figure"]
        assert figure["layout"]["yaxis"]["type"] == "log"
        assert figure["layout"]["yaxis"]["title"]["text"] == f"{label} (logarithmisch)"
    assert data["views"]["de"]["aufrufe_erster_tag"]["rows"] == []
    channels = youtube_render.render_channels_html(payload)
    assert "&lt;b&gt;Mitte&lt;/b&gt;" in channels and "<b>Mitte</b>" not in channels
    assert channels.count('class="ansicht"') == 3  # Deutsch, Englisch, Deutsch & Englisch
    assert "Staatliche und private Medienhäuser (1)" in channels
    assert "öffentlich-rechtlich" in channels
    youtube_render.write_html(payload, tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {"youtube.html", "kanaele.html"}


@pytest.mark.parametrize(
    ("art", "lager", "expected"),
    [
        ("oeffentlich", "mitte", "medienhaus"),
        ("privat", "rechts", "medienhaus"),
        ("privat", "alternativ", "unabhaengig"),  # new media
        ("unabhaengig", "mitte", "unabhaengig"),
        ("organisation", "mitte", "unabhaengig"),
    ],
)
def test_group(art, lager, expected):
    assert youtube_render.group({"art": art, "lager": lager}) == expected


def test_subscribers_text():
    assert youtube_render.subscribers_text(396_000) == "396.000"
    assert youtube_render.subscribers_text(44_800_000) == "44,8 Mio."
    assert youtube_render.subscribers_text(None) == ""


def test_subscriber_history_keeps_one_count_per_day_and_at_most_21_days():
    old_day = (NOW - timedelta(days=22)).date().isoformat()
    kept_day = (NOW - timedelta(days=20)).date().isoformat()
    history = {"UCa": {old_day: 900, kept_day: 1000}, "UCgone": {old_day: 5}}
    history = youtube.update_subscriber_history(history, {"UCa": 1100, "UCb": None}, NOW)
    today = NOW.date().isoformat()
    assert history == {"UCa": {kept_day: 1000, today: 1100}}  # UCgone and UCb left out
    later = NOW + timedelta(hours=3)
    history = youtube.update_subscriber_history(history, {"UCa": 1200}, later)
    assert history["UCa"][today] == 1200  # last count of the day


def test_subscriber_change():
    today = NOW.date().isoformat()
    week = (NOW - timedelta(days=7)).date().isoformat()
    days = {week: 2000, today: 2100}
    assert youtube.subscriber_change(days, NOW) == {
        "seit": week,
        "absolut": 100,
        "relativ_pct": 5.0,
    }
    empty = {"seit": None, "absolut": None, "relativ_pct": None}
    assert youtube.subscriber_change({today: 2100}, NOW) == empty  # first day
    assert youtube.subscriber_change(None, NOW) == empty


def test_channel_list_sorted_by_growth_with_change_columns():
    def entry(name, absolute, relative):
        return {
            "name": name,
            "abo_veraenderung": {
                "seit": "2026-11-17",
                "absolut": absolute,
                "relativ_pct": relative,
            },
        }

    channels = [entry("B", 500, 1.0), entry("a", 100, 5.0), entry("C", None, None)]
    assert [c["name"] for c in youtube_render.sort_channels(channels)] == ["a", "B", "C"]
    by_absolute = youtube_render.sort_channels(channels, "absolut")
    assert [c["name"] for c in by_absolute] == ["B", "a", "C"]
    assert [c["name"] for c in youtube_render.sort_channels(channels, "name")] == ["a", "B", "C"]
    assert youtube_render.change_text({"absolut": 12000, "relativ_pct": 1.25}) == (
        "+12.000",
        "+1,2 %",
    )
    assert youtube_render.change_text({"absolut": -500, "relativ_pct": -0.5}) == ("−500", "−0,5 %")
    assert youtube_render.change_text({"absolut": 0, "relativ_pct": 0.0}) == ("± 0", "± 0 %")
    assert youtube_render.change_text({"absolut": None}) == ("", "")


def test_channel_page_shows_change_and_sort_buttons():
    channels = [channel(name="Kanal A", kanal_id="UCa"), channel(name="Kanal B", kanal_id="UCb")]
    week = (NOW - timedelta(days=7)).date().isoformat()
    history = {"UCa": {week: 1000}, "UCb": {week: 1000}}
    subscribers = {"UCa": 1010, "UCb": 1100}
    history = youtube.update_subscriber_history(history, subscribers, NOW)
    payload = youtube.build_payload([], NOW, [], channels, subscribers, {}, history)
    assert payload["kanaele"][1]["abo_veraenderung"]["relativ_pct"] == 10.0
    html = youtube_render.render_channels_html(payload)
    assert 'data-sort="relativ" aria-pressed="true"' in html
    assert "Alphabetisch" in html and "Veränderung" in html and "+10,0 %" in html
    assert html.index("Kanal B") < html.index("Kanal A")  # stronger growth first
    assert "documentElement.scrollHeight" not in html
