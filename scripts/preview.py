"""Lokale Vorschau: grafik.html eingebettet wie auf deutschlandmonitor.info.

    uv run scripts/preview.py --data-dir daten --plotly <pfad>/plotly.min.js

Baut grafik.html aus <data-dir>/daten.json neu und legt sie wie auf dem Server ab
(/medienmonitor/grafik.html, /assets/plotly.min.js); /index.html bettet sie per iframe
ein wie seite/medienmonitor.qmd. Ohne --plotly wird plotly.min.js einmal von cdn.plot.ly
geladen.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import tempfile
import urllib.request
from pathlib import Path

from medienmonitor import render

ROOT = Path(__file__).resolve().parent.parent
PLOTLY_CDN = "https://cdn.plot.ly/plotly-3.0.1.min.js"


def embed_page() -> str:
    """The HTML block of seite/medienmonitor.qmd inside a plain page."""
    page = (ROOT / "seite" / "medienmonitor.qmd").read_text(encoding="utf-8")
    block = re.search(r"```\{=html\}\n(.*?)\n```", page, re.S).group(1)
    return (
        '<!doctype html><html lang="de"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Medienmonitor – Vorschau</title>"
        '<body style="max-width:1100px;margin:1rem auto;padding:0 1rem;font-family:system-ui">'
        f"<h1>Medienmonitor</h1>{block}</body></html>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "daten")
    parser.add_argument("--plotly", type=Path, help="Pfad zu plotly.min.js")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    target = Path(tempfile.mkdtemp(prefix="medienmonitor-"))
    payload = json.loads((args.data_dir / "daten.json").read_text(encoding="utf-8"))
    render.write_html(payload, target / "medienmonitor" / "grafik.html")
    (target / "index.html").write_text(embed_page(), encoding="utf-8")
    (target / "assets").mkdir()
    plotly = target / "assets" / "plotly.min.js"
    if args.plotly:
        plotly.write_bytes(args.plotly.read_bytes())
    else:
        urllib.request.urlretrieve(PLOTLY_CDN, plotly)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=target)
    print(f"Vorschau: http://localhost:{args.port}/  (Ende mit Strg+C)")
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
