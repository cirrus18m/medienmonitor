from datetime import UTC, datetime
from pathlib import Path

from medienmonitor import feeds, store

ROOT = Path(__file__).resolve().parent.parent
FEED = feeds.Feed("Test", "https://example.org", "DE", "https://example.org/rss", "mitte", "mitte")
RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>T</title>
<item><title>Bundestag beschlie&#223;t &lt;b&gt;Haushalt&lt;/b&gt;</title>
  <link>https://example.org/a/1/?utm_source=rss#top</link>
  <pubDate>Mon, 23 Nov 2026 10:00:00 +0100</pubDate></item>
<item><title>  </title><link>https://example.org/leer</link></item>
<item><title>Ohne Datum</title><link>https://example.org/b</link></item>
</channel></rss>"""
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def test_feeds_yaml_is_complete():
    feed_list = feeds.load_feeds(ROOT / "feeds.yaml", only_active=False)
    assert len(feed_list) > 30
    assert len(feeds.load_feeds(ROOT / "feeds.yaml")) < len(feed_list)
    assert {f.lager for f in feed_list} == {"links", "mitte", "rechts", "alternativ"}
    assert len({f.name for f in feed_list}) == len(feed_list)


def test_normalize_url_drops_tracking_and_fragment():
    assert feeds.normalize_url("HTTPS://Example.org/a/1/?utm_source=rss&id=3#top") == (
        "https://example.org/a/1?id=3"
    )
    assert feeds.headline_id("https://example.org/a/1/") == feeds.headline_id(
        "https://example.org/a/1?utm_medium=x"
    )


def test_parse_feed():
    items = feeds.parse_feed(RSS, FEED, NOW)
    assert [h.titel for h in items] == ["Bundestag beschließt Haushalt", "Ohne Datum"]
    assert items[0].veroeffentlicht == "2026-11-23T09:00:00+00:00"
    assert items[1].veroeffentlicht is None
    assert items[0].lager == "mitte" and items[0].abgerufen == "2026-11-23T12:00:00+00:00"


def test_append_new_dedupes(tmp_path):
    items = feeds.parse_feed(RSS, FEED, NOW)
    assert len(store.append_new(tmp_path, items, NOW)) == 2
    assert store.append_new(tmp_path, items, NOW) == []
    rows = store.read_day(tmp_path, NOW.date())
    assert [r["titel"] for r in rows] == ["Bundestag beschließt Haushalt", "Ohne Datum"]
    assert store.day_file(tmp_path, NOW.date()).relative_to(tmp_path).as_posix() == (
        "titel/2026/11/23.jsonl"
    )
