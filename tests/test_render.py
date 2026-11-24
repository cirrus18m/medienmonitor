import json
from datetime import UTC, datetime

from medienmonitor import render

NOW = datetime(2026, 11, 24, 12, 17, tzinfo=UTC)


def payload():
    article = {
        "quelle": "taz",
        "lager": "links",
        "spektrum": "links",
        "titel": "Haushalt </script><script>alert(1)</script>",
        "url": "javascript:alert(1)",
        "zeit": NOW.isoformat(),
    }
    return {
        "schema": 1,
        "stand": "2026-11-24T13:17+01:00",
        "fenster_stunden": 24,
        "gruppen": {"lager": ["links", "mitte", "rechts", "alternativ"], "spektrum": ["links"]},
        "artikel_je_gruppe": {"lager": {"links": 4, "alternativ": 2}, "spektrum": {"links": 6}},
        "artikel_gesamt": 1234,
        "artikel_zugeordnet": 6,
        "quellen_gesamt": 3,
        "medien": [
            {
                "name": "taz",
                "lager": "links",
                "spektrum": "links",
                "land": "DE",
                "domain": "https://taz.de",
                "artikel": 4,
                "neueste": [
                    {
                        "titel": "Wetter",
                        "url": "https://taz.de/w",
                        "zeit": NOW.isoformat(),
                        "thema": None,
                    }
                ],
            },
            {
                "name": "NIUS",
                "lager": "alternativ",
                "spektrum": "rechts",
                "land": "DE",
                "domain": "javascript:alert(1)",
                "artikel": 2,
            },
            {
                "name": "Welt",
                "lager": "rechts",
                "spektrum": "mitte-rechts",
                "land": "DE",
                "artikel": 0,
            },
        ],
        "themen": [
            {
                "id": "T1",
                "name": "Bundeshaushalt 2027",
                "beschreibung": "Etat.",
                "anzahl_gesamt": 3,
                "quellen": 2,
                "anzahl": {"lager": {"links": 2, "alternativ": 1}, "spektrum": {"links": 3}},
                "anzahl_medium": {"taz": 2, "NIUS": 1},
                "anteil_pct": {
                    "lager": {"links": 50.0, "mitte": 0.0, "rechts": 0.0, "alternativ": 50.0},
                    "spektrum": {"links": 50.0},
                },
                "artikel": [article],
            }
        ],
    }


def test_media_order_new_media_on_top_alphabetical():
    names = [m["name"] for m in render.media_order(payload()["medien"])]
    assert names == ["NIUS", "taz", "Welt"]
    media = [{"name": name, "lager": "mitte"} for name in ("Zeit", "Überblick", "ORF", "Bild")] + [
        {"name": "apolut", "lager": "alternativ"},
        {"name": "AUF1", "lager": "alternativ"},
    ]
    ordered = [m["name"] for m in render.media_order(media)]
    assert ordered == ["apolut", "AUF1", "Bild", "ORF", "Überblick", "Zeit"]


def test_figure_by_medium_counts_and_rows():
    figure = render.figure_by_medium(payload())
    trace = figure.data[0]
    rows = figure.layout.meta["kurz"]
    assert rows == ["Welt", "taz", "NIUS"]  # bottom-up: established first
    assert trace.z[rows.index("taz")][0] == 2
    assert trace.z[rows.index("NIUS")][0] == 1
    assert trace.z[rows.index("Welt")][0] == 0
    assert trace.text[rows.index("Welt")][0] == ""
    assert trace.customdata[rows.index("taz")][0][4:6] == ["T1", "taz"]
    assert figure.layout.meta["medien"] == ["Welt", "taz", "NIUS"]


def test_figure_by_medium_hover_titles_and_links():
    figure = render.figure_by_medium(payload())
    trace = figure.data[0]
    rows = figure.layout.meta["medien"]
    hover = trace.customdata[rows.index("taz")][0][6]
    assert "&lt;/script&gt;" in hover and "<script>" not in hover  # escaped headline
    assert "Klick" in trace.customdata[rows.index("Welt")][0][6]  # empty cell
    labels = figure.layout.yaxis.ticktext
    assert '<a href="https://taz.de" target="_blank"' in labels[rows.index("taz")]
    assert "<a " not in labels[rows.index("NIUS")]  # no javascript: link
    assert {a["text"] for a in figure.layout.annotations} == {"Alte Medien", "Neue Medien"}


def test_hover_titles_are_limited():
    articles = [{"titel": f"T{i}", "zeit": NOW.isoformat()} for i in range(15)]
    text = render.hover_titles(articles)
    assert text.count("<br>") == render.MAX_HOVER_TITLES
    assert text.startswith("Di 13:17 T0") and text.endswith("… und 3 weitere")


def test_figure_by_group_counts():
    trace = render.figure_by_group(payload(), "lager").data[0]
    assert list(trace.z[0]) == [2, 0, 0, 1]


def test_render_html_escapes_foreign_text():
    html = render.render_html(payload())
    assert "Stand: 24.11.2026, 13:17 Uhr" in html and "1.234 Schlagzeilen" in html
    assert "<script>alert(1)" not in html  # headline cannot close the data script
    data = html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
    parsed = json.loads(data)
    assert parsed["themen"]["T1"]["artikel"][0][3].startswith("Haushalt </script>")
    assert set(parsed["figures"]) == {"medium", "lager", "spektrum"}
    assert render.PLOTLY_SRC in html and "cdn" not in html
    assert parsed["medien"]["taz"] == {
        "domain": "https://taz.de",
        "neueste": [["Wetter", "https://taz.de/w", NOW.isoformat(), None]],
    }
    assert parsed["medien"]["NIUS"]["domain"] is None
