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
from medienmonitor.youtube import TOP_N

# Groups: color AND symbol differ (readable without colors), colors of deutschlandmonitor.
GROUPS = (
    # key, label, color, symbol
    ("medienhaus", "Staatliche und private Medienhäuser", "#0077BB", "circle"),
    ("unabhaengig", "Unabhängige Kanäle, Organisationen und neue Medien", "#EE7733", "diamond"),
)
MEDIA_HOUSES = ("oeffentlich", "privat")  # values of "art" in youtube.yaml
VIEWS = (("de", "Deutsch"), ("en", "Englisch"), ("alle", "Deutsch & Englisch"))
# sort keys: key in youtube.json, button, axis title, hint over the chart
METRICS = (
    (
        "aufrufe",
        "Aufrufe",
        "Aufrufe",
        "Die {n} meistgesehenen Videos der letzten Tage. Ältere Videos hatten mehr Zeit, "
        "Aufrufe zu sammeln; vergleichbarer sind die Aufrufe je Tag.",
    ),
    (
        "aufrufe_je_tag",
        "Aufrufe je Tag",
        "Aufrufe je Tag",
        "Die {n} Videos der letzten Tage mit den meisten Aufrufen je Tag online.",
    ),
    (
        "aufrufe_erster_tag",
        "Aufrufe am ersten Tag",
        "Aufrufe am ersten Tag",
        "Die {n} Videos der letzten Tage mit den meisten Aufrufen in den ersten 24 Stunden. "
        "Den Wert gibt YouTube nicht an: Er wird aus den Abfragen alle 3 Stunden geschätzt "
        "und fehlt bei Videos, die bei der ersten Abfrage schon älter als einen Tag waren.",
    ),
)
LANGUAGE_LABELS = {"de": "Deutsch", "en": "Englisch", "mehrsprachig": "mehrsprachig"}
ART_LABELS = {
    "oeffentlich": "öffentlich-rechtlich",
    "privat": "privat",
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


def group(entry: dict) -> str:
    """Group of a video or channel: media houses unless the channel is a new medium."""
    if entry["art"] in MEDIA_HOUSES and entry["lager"] != "alternativ":
        return "medienhaus"
    return "unabhaengig"


def duration_text(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f"{hours}:{minutes:02d} h" if hours else f"{minutes} min"


def number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def first_day_text(value: int | None) -> str:
    return "–" if value is None else number(value)


def subscribers_text(value: int | None) -> str:
    """German short form: 396.000, 2,14 Mio.; empty if hidden."""
    if value is None:
        return ""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.3g}".replace(".", ",") + " Mio."
    return number(value)


def figure(videos: list[dict], days: int, metric: str = "aufrufe", title: str = "Aufrufe"):
    fig = go.Figure()
    for key, label, color, symbol in GROUPS:
        chosen = [v for v in videos if group(v) == key]
        if not chosen:
            continue
        fig.add_trace(
            go.Scatter(
                name=label,
                x=[v["tage_online"] for v in chosen],
                y=[v[metric] for v in chosen],
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
                        first_day_text(v["aufrufe_erster_tag"]),
                    ]
                    for v in chosen
                ],
                hovertemplate=(
                    "<b>%{customdata[0]}. %{customdata[1]}</b><br>%{customdata[2]} "
                    "(%{customdata[6]} Abonnenten) · %{customdata[3]}<br>%{customdata[4]} "
                    "Aufrufe, %{customdata[5]} je Tag, %{customdata[7]} am ersten Tag"
                    "<extra></extra>"
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
                "title": {"text": f"{title} (logarithmisch)"},
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
            first_day_text(v["aufrufe_erster_tag"]),
        ]
        for v in videos
    ]


def _stand(payload: dict) -> str:
    stand = datetime.fromisoformat(payload["stand"])
    return f"Stand: {stand:%d.%m.%Y, %H:%M} Uhr"


def render_html(payload: dict) -> str:
    days = payload["fenster_tage"]
    lists = payload["listen"]
    views = {}
    for key, _ in VIEWS:
        stand = (
            f"{_stand(payload)} · letzte {days} Tage · "
            f"{number(payload['gezaehlt_je_liste'][key])} Videos länger als "
            f"{payload['mindestdauer_min']} Minuten"
        )
        views[key] = {
            metric: {
                "figure": figure(lists[key][metric], days, metric, title).to_plotly_json(),
                "rows": _rows(lists[key][metric]),
                "stand": stand,
                "hinweis": hint.format(n=len(lists[key][metric]) or TOP_N)
                + f" Nur Videos länger als {payload['mindestdauer_min']} Minuten, ohne "
                "Livestreams und regelmäßige Nachrichtensendungen.",
            }
            for metric, _, title, hint in METRICS
        }
    language_buttons = "".join(
        f'<button type="button" data-view="{key}">{escape(label)}</button>' for key, label in VIEWS
    )
    metric_buttons = "".join(
        f'<button type="button" data-metric="{key}">{escape(label)}</button>'
        for key, label, _, _ in METRICS
    )
    data = {
        "views": views,
        "groups": {key: label for key, label, _, _ in GROUPS},
        "metrics": [key for key, _, _, _ in METRICS],
    }
    template = (Path(__file__).parent / "youtube_template.html").read_text(encoding="utf-8")
    return (
        template.replace("{{PLOTLY_SRC}}", PLOTLY_SRC)
        .replace("{{BUTTONS}}", language_buttons)
        .replace("{{METRIC_BUTTONS}}", metric_buttons)
        .replace("{{SOURCE}}", escape(SOURCE))
        .replace("{{DATA}}", _json(data))
    )


def _channel_table(channels: list[dict], both: bool) -> str:
    rows = []
    for c in channels:
        handle = f' <span class="grau">{escape(c["handle"])}</span>' if c["handle"] else ""
        language = c["sprache"].upper() if c["sprache"] in ("de", "en") else "mehrspr."
        tag = f' <span class="grau">{escape(language)}</span>' if both else ""
        kind = "Neue Medien" if c["lager"] == "alternativ" else ART_LABELS.get(c["art"], c["art"])
        rows.append(
            "<tr>"
            f'<td><a href="{escape(c["url"])}" target="_blank" '
            f'rel="noopener nofollow noreferrer">{escape(c["name"])}</a>{handle}{tag}</td>'
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


def _in_view(channel: dict, view: str) -> bool:
    """Multilingual channels appear in every view: their videos count by video language."""
    return view == "alle" or channel["sprache"] in (view, "mehrsprachig")


def render_channels_html(payload: dict) -> str:
    views = []
    for view, _ in VIEWS:
        in_view = [c for c in payload["kanaele"] if _in_view(c, view)]
        sections = []
        for key, label, _, _ in GROUPS:
            chosen = [c for c in in_view if group(c) == key]
            if chosen:
                sections.append(
                    f'<h2><span class="zeichen {key}"></span>{escape(label)} '
                    f"({len(chosen)})</h2>" + _channel_table(chosen, view == "alle")
                )
        hidden = "" if view == VIEWS[0][0] else " hidden"
        views.append(
            f'<div class="ansicht" data-view="{view}"{hidden}>'
            f"<p>{len(in_view)} Kanäle</p>" + "\n".join(sections) + "</div>"
        )
    buttons = "".join(
        f'<button type="button" data-view="{key}" aria-pressed="{str(i == 0).lower()}">'
        f"{escape(label)}</button>"
        for i, (key, label) in enumerate(VIEWS)
    )
    numbers = (
        f"{_stand(payload)} · „Videos“: veröffentlicht in den letzten "
        f"{payload['fenster_tage']} Tagen; „davon gezählt“: länger als "
        f"{payload['mindestdauer_min']} Minuten, ohne Livestreams und Nachrichtensendungen. "
        "Mehrsprachige Kanäle stehen in jeder Auswahl."
    )
    template = (Path(__file__).parent / "kanaele_template.html").read_text(encoding="utf-8")
    return (
        template.replace("{{STAND}}", escape(numbers))
        .replace("{{BUTTONS}}", buttons)
        .replace("{{SECTIONS}}", "\n".join(views))
        .replace("{{SOURCE}}", escape(SOURCE))
    )


def write_html(payload: dict, directory: Path) -> None:
    """youtube.html and kanaele.html in ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "youtube.html").write_text(render_html(payload), encoding="utf-8")
    (directory / "kanaele.html").write_text(render_channels_html(payload), encoding="utf-8")
