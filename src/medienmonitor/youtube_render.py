"""Build youtube.html (scatter "Aufrufe über Tage online" and top list, per language) and
kanaele.html (overview of the channels) from youtube.json.

Like grafik.html (render.py) both are embedded by deutschlandmonitor.info (iframe, same
domain) and load nothing from YouTube/Google: no embedded videos, no thumbnails.
plotly.min.js comes from the same server. Titles come from foreign channels and are set
only via textContent (youtube.html) or escaped (kanaele.html); links only to
https://www.youtube.com.
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
    ("etabliert", "Medienhäuser, unabhängige Kanäle, Organisationen", "#0077BB", "circle"),
    ("neu", "Neue Medien", "#EE7733", "diamond"),
)
VIEWS = (("de", "Deutsch"), ("en", "Englisch"), ("alle", "Deutsch & Englisch"))
LANGUAGE_LABELS = {"de": "Deutsch", "en": "Englisch", "mehrsprachig": "Mehrsprachig"}
ART_LABELS = {
    "medienhaus": "Medienhaus",
    "unabhaengig": "unabhängig",
    "organisation": "Organisation",
}
SPECTRUM_LABELS = {
    "links": "links",
    "mitte-links": "Mitte-links",
    "mitte": "Mitte",
    "mitte-rechts": "Mitte-rechts",
    "rechts": "rechts",
    "unklar": "–",
}
TICKS = [m * 10**e for e in range(1, 9) for m in (1, 2, 5)]
SOURCE = (
    "Quelle: YouTube Data API (Aufrufe und Abonnenten zum Stand); Auswahl der Kanäle und "
    "Einordnung: eigene Einschätzung"
)


def group(video: dict) -> str:
    return "neu" if video["lager"] == "alternativ" else "etabliert"


def duration_text(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f"{hours}:{minutes:02d} h" if hours else f"{minutes} min"


def number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def subscribers_text(value: int | None) -> str:
    """German short form: 396.000, 2,14 Mio.; empty if hidden."""
    if value is None:
        return ""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.3g}".replace(".", ",") + " Mio."
    return number(value)


def figure(videos: list[dict], days: int) -> go.Figure:
    fig = go.Figure()
    for key, label, color, symbol in GROUPS:
        chosen = [v for v in videos if group(v) == key]
        if not chosen:
            continue
        fig.add_trace(
            go.Scatter(
                name=label,
                x=[v["tage_online"] for v in chosen],
                y=[v["aufrufe"] for v in chosen],
                mode="markers+text",
                text=[str(v["rang"]) for v in chosen],
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
                        subscribers_text(v["abonnenten"]) or "verborgen",
                    ]
                    for v in chosen
                ],
                hovertemplate=(
                    "<b>%{customdata[0]}. %{customdata[1]}</b><br>%{customdata[2]} "
                    "(%{customdata[6]} Abonnenten) · %{customdata[3]}<br>%{customdata[4]} "
                    "Aufrufe, %{customdata[5]} je Tag<extra></extra>"
                ),
            )
        )
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
                # 1-2-5 steps, labels in German format (10.000, 20.000, 50.000 …)
                "tickvals": TICKS,
                "ticktext": [number(t) for t in TICKS],
                "fixedrange": True,
                "automargin": True,
            },
        )
    )
    return fig


def _rows(videos: list[dict]) -> list[list]:
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
            subscribers_text(v["abonnenten"]),
            v["sprache"].upper(),
        ]
        for v in videos
    ]


def _stand(payload: dict) -> str:
    stand = datetime.fromisoformat(payload["stand"])
    return f"Stand: {stand:%d.%m.%Y, %H:%M} Uhr"


def render_html(payload: dict) -> str:
    days = payload["fenster_tage"]
    lists = payload["listen"]
    views = {
        key: {
            "figure": figure(lists[key], days).to_plotly_json(),
            "rows": _rows(lists[key]),
            "stand": (
                f"{_stand(payload)} · letzte {days} Tage · "
                f"{number(payload['gezaehlt_je_liste'][key])} Videos länger als "
                f"{payload['mindestdauer_min']} Minuten"
            ),
        }
        for key, _ in VIEWS
    }
    buttons = "".join(
        f'<button type="button" data-view="{key}">{escape(label)}</button>' for key, label in VIEWS
    )
    data = {"views": views, "groups": {key: label for key, label, _, _ in GROUPS}}
    template = (Path(__file__).parent / "youtube_template.html").read_text(encoding="utf-8")
    return (
        template.replace("{{PLOTLY_SRC}}", PLOTLY_SRC)
        .replace("{{BUTTONS}}", buttons)
        .replace("{{SOURCE}}", escape(SOURCE))
        .replace("{{DATA}}", _json(data))
    )


def _channel_table(channels: list[dict]) -> str:
    rows = []
    for c in channels:
        handle = f' <span class="grau">{escape(c["handle"])}</span>' if c["handle"] else ""
        kind = "Neue Medien" if c["lager"] == "alternativ" else ART_LABELS.get(c["art"], c["art"])
        rows.append(
            "<tr>"
            f'<td><a href="{escape(c["url"])}" target="_blank" '
            f'rel="noopener nofollow noreferrer">{escape(c["name"])}</a>{handle}</td>'
            f"<td>{escape(c['land'])}</td>"
            f"<td>{escape(kind)}</td>"
            f"<td>{escape(SPECTRUM_LABELS.get(c['spektrum'], c['spektrum']))}</td>"
            f'<td class="zahl">{subscribers_text(c["abonnenten"])}</td>'
            f'<td class="zahl">{c["videos"]}</td>'
            f'<td class="zahl">{c["gezaehlt"]}</td>'
            "</tr>"
        )
    return (
        '<div class="scroll"><table><thead><tr><th>Kanal</th><th>Land</th><th>Art</th>'
        '<th>Spektrum</th><th class="zahl">Abonnenten</th><th class="zahl">Videos</th>'
        '<th class="zahl">davon gezählt</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
    )


def render_channels_html(payload: dict) -> str:
    sections = []
    for key in ("de", "en", "mehrsprachig"):
        chosen = [c for c in payload["kanaele"] if c["sprache"] == key]
        if chosen:
            sections.append(
                f"<h2>{escape(LANGUAGE_LABELS[key])} ({len(chosen)} Kanäle)</h2>"
                + _channel_table(chosen)
            )
    numbers = (
        f"{_stand(payload)} · {len(payload['kanaele'])} Kanäle · „Videos“: veröffentlicht in "
        f"den letzten {payload['fenster_tage']} Tagen; „davon gezählt“: länger als "
        f"{payload['mindestdauer_min']} Minuten, ohne Livestreams und Nachrichtensendungen"
    )
    template = (Path(__file__).parent / "kanaele_template.html").read_text(encoding="utf-8")
    return (
        template.replace("{{STAND}}", escape(numbers))
        .replace("{{SECTIONS}}", "\n".join(sections))
        .replace("{{SOURCE}}", escape(SOURCE))
    )


def write_html(payload: dict, directory: Path) -> None:
    """youtube.html and kanaele.html in ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "youtube.html").write_text(render_html(payload), encoding="utf-8")
    (directory / "kanaele.html").write_text(render_channels_html(payload), encoding="utf-8")
