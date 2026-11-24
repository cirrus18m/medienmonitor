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
NEW_MEDIA = "alternativ"  # lager of media that position themselves against the rest
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


def _number(value: float) -> str:
    """German number for cell labels: one decimal below 10, else whole numbers."""
    if value <= 0:
        return ""
    text = f"{value:.1f}" if value < 10 else f"{value:.0f}"
    return text.replace(".", ",")


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


def media_order(media: list[dict]) -> list[dict]:
    """New media first, then established media; each from left to right, then by name."""

    def key(medium: dict) -> tuple:
        spectrum = medium["spektrum"]
        rank = SPECTRUM_ORDER.index(spectrum) if spectrum in SPECTRUM_ORDER else 99
        return (medium["lager"] != NEW_MEDIA, rank, medium["name"].casefold())

    return sorted(media, key=key)


def figure_by_medium(payload: dict) -> go.Figure:
    """Rows = media (new media on top), columns = topics; value = share of the medium's
    headlines on the topic in percent."""
    columns = payload["themen"][:MAX_TOPIC_COLUMNS]
    media = list(reversed(media_order(payload["medien"])))  # Plotly draws rows bottom-up
    z, text, custom = [], [], []
    for medium in media:
        row_z, row_text, row_custom = [], [], []
        for topic in columns:
            count = topic.get("anzahl_medium", {}).get(medium["name"], 0)
            share = 100 * count / medium["artikel"] if medium["artikel"] else 0.0
            row_z.append(round(share, 2))
            row_text.append(_number(share))
            spectrum = LABELS["spektrum"].get(medium["spektrum"], medium["spektrum"])
            row_custom.append(
                [count, medium["artikel"], topic["name"], spectrum, topic["id"], medium["name"]]
            )
        z.append(row_z)
        text.append(row_text)
        custom.append(row_custom)

    established = sum(1 for m in media if m["lager"] != NEW_MEDIA)
    ticktext = [
        f"{escape(m['name'])} <span style='color:{GREY}'>· "
        f"{LABELS['spektrum'].get(m['spektrum'], m['spektrum'])} · {m['artikel']}</span>"
        for m in media
    ]
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
            hovertemplate=(
                "<b>%{customdata[5]}</b>: %{customdata[2]}<br>"
                "%{z:.1f} % der Schlagzeilen des Mediums (%{customdata[0]} von "
                "%{customdata[1]})<br>Spektrum: %{customdata[3]}<extra></extra>"
            ),
        )
    )
    band = {"xref": "paper", "x": 1, "xanchor": "left", "textangle": 90, "showarrow": False}
    annotations = []
    if established:
        annotations.append(
            {**band, "y": (established - 1) / 2, "text": "Etablierte Medien", "yref": "y"}
        )
    if established < len(media):
        annotations.append(
            {**band, "y": (established + len(media) - 1) / 2, "text": "Neue Medien", "yref": "y"}
        )
    shapes = []
    if 0 < established < len(media):
        shapes.append(
            {
                "type": "line",
                "xref": "paper",
                "x0": 0,
                "x1": 1,
                "yref": "y",
                "y0": established - 0.5,
                "y1": established - 0.5,
                "line": {"color": NEUTRAL, "width": 2},
            }
        )
    figure.update_layout(
        **_layout(
            230 + 22 * len(media),
            margin={"l": 10, "r": 28, "t": 10, "b": 10},
            annotations=annotations,
            shapes=shapes,
            # names without spectrum and count, used by the page on narrow screens
            meta={"kurz": [escape(shorten(m["name"], 18)) for m in media]},
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
                "ticktext": ticktext,
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
        shares = [topic["anteil_pct"][grouping].get(g, 0.0) for g in groups]
        z.append(shares)
        text.append([_number(v) for v in shares])
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
                "<b>%{customdata[2]}</b><br>%{customdata[3]}: %{z:.1f} % der Schlagzeilen "
                "(%{customdata[0]} von %{customdata[1]})<extra></extra>"
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
        "Anteil an allen Schlagzeilen des Mediums in den letzten 24 Stunden in %. Oben "
        "neue Medien, unten etablierte, jeweils von links nach rechts; hinter dem Namen "
        "Spektrum und Zahl der Schlagzeilen. Bei wenigen Schlagzeilen schwanken die Anteile "
        "stark."
    ),
    "lager": "Anteil an allen Schlagzeilen des Lagers in den letzten 24 Stunden in %.",
    "spektrum": "Anteil an allen Schlagzeilen der Gruppe in den letzten 24 Stunden in %.",
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
