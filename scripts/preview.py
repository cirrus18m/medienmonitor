"""Lokale Vorschau der Seite: daten.json + seite/ in einem Ordner, Webserver auf Port 8765.

    uv run scripts/preview.py --data-dir daten

plotly.min.js kommt aus dem installierten Plotly des deutschlandmonitor-Repos
(Pfad mit --plotly angeben) oder wird einmal von cdn.plot.ly geladen.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "daten")
    parser.add_argument("--plotly", type=Path, help="Pfad zu plotly.min.js")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    target = Path(tempfile.mkdtemp(prefix="medienmonitor-"))
    shutil.copy(ROOT / "seite" / "vorschau.html", target / "index.html")
    shutil.copy(ROOT / "seite" / "medienmonitor.js", target)
    shutil.copy(args.data_dir / "daten.json", target)
    if args.plotly:
        shutil.copy(args.plotly, target / "plotly.min.js")
    else:
        urllib.request.urlretrieve(PLOTLY_CDN, target / "plotly.min.js")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=target)
    print(f"Vorschau: http://localhost:{args.port}/  (Ende mit Strg+C)")
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
