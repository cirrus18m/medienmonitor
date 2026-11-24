"""Build grafik.html: the charts of the Medienmonitor as one HTML file.

deutschlandmonitor.info embeds the file on its page "Medienmonitor" (iframe, same
domain). The charts are made here with Plotly; the page only adds a view switch and the
list of headlines (with links) for a clicked cell. plotly.min.js comes from the same
server (``/assets/plotly.min.js`` of deutschlandmonitor), so the browser asks no third
party. Headlines and URLs come from foreign feeds: the page script sets them only via
textContent and allows only http(s) links.
"""

from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import plotly.graph_objects as go

# colors.py of deutschlandmonitor: white -> BLUE for ordered values, NEUTRAL text.
BLUE = "#0077BB"
NEUTRAL = "#1B1B1B"
GREY = "#767676"
SCALE = [[0, "#FFFFFF"], [1, BLUE]]
FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
PLOTLY_SRC = "/assets/plotly.min.js"

MAX_TOPIC_ROWS = 20  # views by group: topics as rows
MAX_TOPIC_COLUMNS = 15  # view by medium: topics as columns
MAX_HOVER_TITLES = 12  # headlines listed in the hover box of a cell
NEW_MEDIA = "alternativ"  # lager of media that position themselves against the rest
NEW_MEDIA_LABEL = "Neue Medien"
OLD_MEDIA_LABEL = "Alte Medien"
BERLIN = ZoneInfo("Europe/Berlin")
SPECTRUM_ORDER = ("links", "mitte-links", "mitte", "mitte-rechts", "rechts", "unklar")
LABELS = {
    "lager": {"links": "links", "mitte": "Mitte", "rechts": "rechts", "alternativ": "alternativ"},
    "spektrum": {
        "links": "links",
        "mitte-links": "Mitte-links",
        "mitte": "Mitte",
        "mitte-rechts": "Mitte-rechts",
        "rechts": "rechts",
        "unklar": "unklar",
    },
}
SOURCE = (
    "Quelle: RSS-Schlagzeilen der beobachteten Medien; Zuordnung zu Themen automatisch durch "
    "KI (Claude); Einordnung der Medien: eigene Einschätzung"
)


def shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _number(count: int) -> str:
    """Cell label: the number of headlines, empty for none."""
    return str(count) if count > 0 else ""


def _layout(height: int, **extra) -> dict:
    return {
        "template": "plotly_white",
        "height": height,
        "margin": {"l": 10, "r": 10, "t": 10, "b": 10},
        "separators": ",.",
        "font": {"family": FONT, "size": 12, "color": NEUTRAL},
        "paper_bgcolor": "#FFFFFF",
        "plot_bgcolor": "#FFFFFF",
        **extra,
    }


def sort_key(name: str) -> str:
    """Alphabetical order as in German lists: umlauts like their base letter."""
    text = name.casefold()
    for umlaut, base in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        text = text.replace(umlaut, base)
    return text


def media_order(media: list[dict]) -> list[dict]:
    """New media first, then old media; each group alphabetical."""
    return sorted(media, key=lambda m: (m["lager"] != NEW_MEDIA, sort_key(m["name"])))


def safe_url(url: str | None) -> str | None:
    """Only http(s) addresses become links."""
    if not url:
        return None
    parts = urlsplit(url)
    return url if parts.scheme in ("http", "https") and parts.netloc else None


WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _clock(moment: str) -> str:
    """Weekday and time in Berlin, as in the headline list of the page ("Di 13:17")."""
    local = datetime.fromisoformat(moment).astimezone(BERLIN)
    return f"{WEEKDAYS[local.weekday()]} {local:%H:%M}"


def hover_titles(articles: list[dict]) -> str:
    """Headlines of a cell for the hover box (escaped, newest first)."""
    lines = [
        f"{_clock(a['zeit'])} {escape(shorten(a['titel'], 90))}"
        for a in articles[:MAX_HOVER_TITLES]
    ]
    if len(articles) > MAX_HOVER_TITLES:
        lines.append(f"… und {len(articles) - MAX_HOVER_TITLES} weitere")
    return "<br>".join(lines)


def medium_label(medium: dict) -> str:
    """Tick label: name, a link to the home page, spectrum and number of headlines."""
    spectrum = LABELS["spektrum"].get(medium["spektrum"], medium["spektrum"])
    url = safe_url(medium.get("domain"))
    link = f' <a href="{escape(url)}" target="_blank" style="color:{BLUE}">↗</a>' if url else ""
    return (
        f"{escape(medium['name'])}{link} <span style='color:{GREY}'>· "
        f"{spectrum} · {medium['artikel']}</span>"
    )


def figure_by_medium(payload: dict) -> go.Figure:
    """Rows = media (new media on top), columns = topics; value = number of the medium's
    headlines on the topic. The hover box lists these headlines."""
    columns = payload["themen"][:MAX_TOPIC_COLUMNS]
    media = list(reversed(media_order(payload["medien"])))  # Plotly draws rows bottom-up
    z, text, custom = [], [], []
    for medium in media:
        row_z, row_text, row_custom = [], [], []
        for topic in columns:
            count = topic.get("anzahl_medium", {}).get(medium["name"], 0)
            articles = [a for a in topic["artikel"] if a["quelle"] == medium["name"]]
            row_z.append(count)
            row_text.append(_number(count))
            spectrum = LABELS["spektrum"].get(medium["spektrum"], medium["spektrum"])
            titles = (
                hover_titles(articles)
                if articles
                else "Keine Schlagzeile zum Thema.<br>Klick: die letzten 10 Schlagzeilen "
                "des Mediums"
            )
            row_custom.append(
                [
                    count,
                    medium["artikel"],
                    escape(topic["name"]),
                    spectrum,
                    topic["id"],
                    medium["name"],
                    titles,
                    escape(medium["name"]),
                ]
            )
        z.append(row_z)
        text.append(row_text)
        custom.append(row_custom)

    old = sum(1 for m in media if m["lager"] != NEW_MEDIA)
    figure = go.Figure(
        go.Heatmap(
            x=list(range(len(columns))),
            y=list(range(len(media))),
            z=z,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 10},
            customdata=custom,
            colorscale=SCALE,
            zmin=0,
            xgap=1,
            ygap=1,
            showscale=False,
            hoverongaps=False,
            hoverlabel={"bgcolor": "#FFFFFF", "bordercolor": GREY, "align": "left"},
            hovertemplate=(
                "<b>%{customdata[7]}</b>: %{customdata[2]} · %{z} Schlagzeilen "
                "(von %{customdata[1]} des Mediums)<br>"
                "<span style='color:" + GREY + "'>%{customdata[6]}</span><extra></extra>"
            ),
        )
    )
    band = {"xref": "paper", "x": 1, "xanchor": "left", "textangle": 90, "showarrow": False}
    annotations = []
    if old:
        annotations.append({**band, "y": (old - 1) / 2, "text": OLD_MEDIA_LABEL, "yref": "y"})
    if old < len(media):
        annotations.append(
            {**band, "y": (old + len(media) - 1) / 2, "text": NEW_MEDIA_LABEL, "yref": "y"}
        )
    shapes = []
    if 0 < old < len(media):
        shapes.append(
            {
                "type": "line",
                "xref": "paper",
                "x0": 0,
                "x1": 1,
                "yref": "y",
                "y0": old - 0.5,
                "y1": old - 0.5,
                "line": {"color": NEUTRAL, "width": 2},
            }
        )
    figure.update_layout(
        **_layout(
            230 + 22 * len(media),
            margin={"l": 10, "r": 28, "t": 10, "b": 10},
            annotations=annotations,
            shapes=shapes,
            meta={
                # names without link, spectrum and count, for narrow screens
                "kurz": [escape(shorten(m["name"], 18)) for m in media],
                # row -> medium, for clicks on the name
                "medien": [m["name"] for m in media],
            },
            xaxis={
                "side": "top",
                "fixedrange": True,
                "automargin": True,
                "tickangle": -40,
                "tickvals": list(range(len(columns))),
                "ticktext": [escape(shorten(t["name"], 30)) for t in columns],
            },
            yaxis={
                "fixedrange": True,
                "automargin": True,
                "tickvals": list(range(len(media))),
                "ticktext": [medium_label(m) for m in media],
            },
        )
    )
    return figure


def figure_by_group(payload: dict, grouping: str) -> go.Figure:
    """Rows = topics (largest on top), columns = groups (lager or spektrum)."""
    groups = payload["gruppen"][grouping]
    totals = payload["artikel_je_gruppe"][grouping]
    rows = list(reversed(payload["themen"][:MAX_TOPIC_ROWS]))
    labels = [LABELS[grouping].get(g, g) for g in groups]
    z, text, custom = [], [], []
    for topic in rows:
        counts = [topic["anzahl"][grouping].get(g, 0) for g in groups]
        z.append(counts)
        text.append([_number(v) for v in counts])
        custom.append(
            [
                [
                    topic["anzahl"][grouping].get(g, 0),
                    totals.get(g, 0),
                    topic["name"],
                    label,
                    topic["id"],
                    g,
                ]
                for g, label in zip(groups, labels, strict=True)
            ]
        )
    figure = go.Figure(
        go.Heatmap(
            x=labels,
            y=list(range(len(rows))),
            z=z,
            text=text,
            texttemplate="%{text}",
            customdata=custom,
            colorscale=SCALE,
            zmin=0,
            xgap=2,
            ygap=2,
            showscale=False,
            hoverongaps=False,
            hovertemplate=(
                "<b>%{customdata[2]}</b><br>%{customdata[3]}: %{z} Schlagzeilen "
                "(von %{customdata[1]} der Gruppe)<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        **_layout(
            90 + 28 * len(rows),
            xaxis={"side": "top", "fixedrange": True, "automargin": True, "tickangle": 0},
            yaxis={
                "fixedrange": True,
                "automargin": True,
                "tickvals": list(range(len(rows))),
                "ticktext": [escape(shorten(t["name"], 45)) for t in rows],
            },
        )
    )
    return figure


VIEWS = (
    ("medium", "je Medium"),
    ("lager", "nach Lager"),
    ("spektrum", "nach Spektrum"),
)
NOTES = {
    "medium": (
        "Zahl der Schlagzeilen je Medium und Thema in den letzten 24 Stunden. Oben neue "
        "Medien, unten alte, jeweils alphabetisch; hinter dem Namen ↗ (Website), Spektrum "
        "und Zahl aller Schlagzeilen des Mediums. Medien mit vielen Meldungen fallen stärker "
        "ins Gewicht. Ein Feld mit Zahl anklicken: die Schlagzeilen mit Links; ein leeres "
        "Feld oder den Namen anklicken: die letzten 10 Schlagzeilen des Mediums."
    ),
    "lager": "Zahl der Schlagzeilen je Lager und Thema in den letzten 24 Stunden.",
    "spektrum": "Zahl der Schlagzeilen je Spektrum und Thema in den letzten 24 Stunden.",
}


def _articles(payload: dict) -> dict:
    """Topic id -> name, description and articles (only what the list needs)."""
    return {
        t["id"]: {
            "name": t["name"],
            "beschreibung": t["beschreibung"],
            "artikel": [
                [a["quelle"], a["spektrum"], a["lager"], a["titel"], a["url"], a["zeit"]]
                for a in t["artikel"]
            ],
        }
        for t in payload["themen"]
    }


def _media(payload: dict) -> dict:
    """Medium name -> home page and latest headlines (for clicks on name or empty cell)."""
    return {
        m["name"]: {
            "domain": safe_url(m.get("domain")),
            "neueste": [
                [a["titel"], a["url"], a["zeit"], a.get("thema")] for a in m.get("neueste", [])
            ],
        }
        for m in payload.get("medien", [])
    }


def _json(value) -> str:
    """JSON safe inside <script>: no closing tag or HTML comment can appear."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render_html(payload: dict) -> str:
    stand = datetime.fromisoformat(payload["stand"])
    stand_text = f"{stand:%d.%m.%Y, %H:%M} Uhr"
    figures = {}
    if payload.get("medien"):
        figures["medium"] = figure_by_medium(payload).to_plotly_json()
    figures["lager"] = figure_by_group(payload, "lager").to_plotly_json()
    figures["spektrum"] = figure_by_group(payload, "spektrum").to_plotly_json()
    views = [(key, label) for key, label in VIEWS if key in figures]
    buttons = "".join(
        f'<button type="button" data-view="{key}">{escape(label)}</button>' for key, label in views
    )
    total = f"{payload['artikel_gesamt']:,}".replace(",", ".")
    numbers = (
        f"Stand: {stand_text} · letzte {payload['fenster_stunden']} Stunden · "
        f"{total} Schlagzeilen aus {payload['quellen_gesamt']} Medien"
    )
    data = {
        "figures": figures,
        "notes": {k: NOTES[k] for k in figures},
        "labels": LABELS,
        "themen": _articles(payload),
        "medien": _media(payload),
        "reihenfolge": [t["id"] for t in payload["themen"][:MAX_TOPIC_ROWS]],
    }
    template = (Path(__file__).parent / "chart_template.html").read_text(encoding="utf-8")
    return (
        template.replace("{{PLOTLY_SRC}}", PLOTLY_SRC)
        .replace("{{STAND}}", escape(numbers))
        .replace("{{BUTTONS}}", buttons)
        .replace("{{SOURCE}}", escape(SOURCE))
        .replace("{{DATA}}", _json(data))
    )


def write_html(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(payload), encoding="utf-8")
