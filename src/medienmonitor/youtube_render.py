"""Build youtube.html: scatter "Aufrufe über Tage online" and the top list as one HTML file.

Like grafik.html (render.py) it is embedded by deutschlandmonitor.info (iframe, same
domain) and loads plotly.min.js from that server. No embedded videos and no thumbnails:
the page loads nothing from YouTube/Google. Titles come from foreign channels and are set
only via textContent; links only to https://www.youtube.com/watch.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

import plotly.graph_objects as go

from medienmonitor.render import PLOTLY_SRC, _json, _layout

# Groups: color AND symbol differ (readable without colors), colors of deutschlandmonitor.
GROUPS = (
    # key, label, color, symbol
    ("etabliert", "Medienhäuser und unabhängige Kanäle", "#0077BB", "circle"),
    ("neu", "Neue Medien", "#EE7733", "diamond"),
    ("politik", "Parteien und Politiker", "#555555", "square"),
)
SOURCE = (
    "Quelle: YouTube Data API (Aufrufe zum Stand); Auswahl der Kanäle und Einordnung: eigene "
    "Einschätzung"
)


def group(video: dict) -> str:
    if video["art"] == "politik":
        return "politik"
    return "neu" if video["lager"] == "alternativ" else "etabliert"


def duration_text(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f"{hours}:{minutes:02d} h" if hours else f"{minutes} min"


def number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def figure(payload: dict) -> go.Figure:
    fig = go.Figure()
    for key, label, color, symbol in GROUPS:
        videos = [v for v in payload["videos"] if group(v) == key]
        if not videos:
            continue
        fig.add_trace(
            go.Scatter(
                name=label,
                x=[v["tage_online"] for v in videos],
                y=[v["aufrufe"] for v in videos],
                mode="markers+text",
                text=[str(v["rang"]) for v in videos],
                textposition="middle right",
                textfont={"size": 10, "color": "#555555"},
                marker={
                    "color": color,
                    "symbol": symbol,
                    "size": 11,
                    "line": {"color": "#FFFFFF", "width": 1},
                },
                customdata=[
                    [
                        v["rang"],
                        v["titel"],
                        v["kanal"],
                        duration_text(v["dauer_s"]),
                        number(v["aufrufe"]),
                        number(v["aufrufe_je_tag"]),
                    ]
                    for v in videos
                ],
                meta={"gruppe": key},
                hovertemplate=(
                    "<b>%{customdata[0]}. %{customdata[1]}</b><br>%{customdata[2]} · "
                    "%{customdata[3]}<br>%{customdata[4]} Aufrufe, %{customdata[5]} je Tag"
                    "<extra></extra>"
                ),
            )
        )
    days = payload["fenster_tage"]
    fig.update_layout(
        **_layout(
            480,
            margin={"l": 10, "r": 10, "t": 10, "b": 10},
            legend={"orientation": "h", "x": 0, "y": 1.02, "yanchor": "bottom"},
            xaxis={
                "title": {"text": "Tage online"},
                "range": [-0.2, days + 0.2],
                "dtick": 1,
                "fixedrange": True,
                "automargin": True,
            },
            yaxis={
                "title": {"text": "Aufrufe (logarithmisch)"},
                "type": "log",
                "dtick": 1,  # only powers of ten: 10.000, 100.000, 1.000.000
                "fixedrange": True,
                "automargin": True,
                "exponentformat": "none",
            },
        )
    )
    return fig


def _rows(payload: dict) -> list[list]:
    return [
        [
            v["rang"],
            group(v),
            v["kanal"],
            v["titel"],
            v["url"],
            duration_text(v["dauer_s"]),
            number(v["aufrufe"]),
            f"{v['tage_online']:.1f}".replace(".", ","),
            number(v["aufrufe_je_tag"]),
        ]
        for v in payload["videos"]
    ]


def render_html(payload: dict) -> str:
    stand = datetime.fromisoformat(payload["stand"])
    numbers = (
        f"Stand: {stand:%d.%m.%Y, %H:%M} Uhr · letzte {payload['fenster_tage']} Tage · "
        f"{payload['videos_gezaehlt']} Videos länger als {payload['mindestdauer_min']} "
        f"Minuten aus {payload['kanaele']} Kanälen"
    )
    data = {
        "figure": figure(payload).to_plotly_json(),
        "rows": _rows(payload),
        "groups": {key: label for key, label, _, _ in GROUPS},
    }
    template = (Path(__file__).parent / "youtube_template.html").read_text(encoding="utf-8")
    return (
        template.replace("{{PLOTLY_SRC}}", PLOTLY_SRC)
        .replace("{{STAND}}", escape(numbers))
        .replace("{{SOURCE}}", escape(SOURCE))
        .replace("{{DATA}}", _json(data))
    )


def write_html(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(payload), encoding="utf-8")
