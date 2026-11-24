# Medienmonitor

Sammelt stündlich die Schlagzeilen deutschsprachiger Medien (RSS-Feeds aus
[feeds.yaml](feeds.yaml)), ordnet sie per KI Themen zu und bereitet für die Seite
„Medienmonitor“ auf deutschlandmonitor.info auf, welche Mediengruppen über welche Themen
berichten.

Gespeichert werden nur Überschrift, Link, Quelle und Zeit, keine Artikeltexte.

## Themen

Jede Stunde gehen nur die neuen Schlagzeilen (ohne Namen des Mediums) mit der Liste der
aktiven Themen an Claude. Die Antwort ordnet jede Schlagzeile einem vorhandenen oder neuen
Thema zu oder „sonstiges“ (Ratgeber, Sport, Unterhaltung). Alle sechs Stunden werden
doppelte Themen zusammengelegt. Die Themenliste steht in `themen.json` im Branch `daten`.
`daten.json` zeigt Themen mit mindestens 5 Artikeln aus 2 Quellen; der Anteil je
Mediengruppe bezieht sich auf alle Artikel dieser Gruppe in den letzten 24 Stunden.

## Befehle

```bash
uv sync                                  # Umgebung
uv run scripts/check_feeds.py            # alle Feeds prüfen
uv run scripts/run_hourly.py             # abrufen, Themen zuordnen, daten.json + grafik.html
uv run scripts/run_hourly.py --no-topics # nur abrufen (ohne KI)
uv run scripts/preview.py --data-dir daten --plotly <pfad>/plotly.min.js  # eingebettet ansehen
uv run pytest && uv run ruff check .
```

## Grafik

Jeder Lauf schreibt neben `daten.json` die Datei `grafik.html`: die Heatmaps (je Medium,
nach Lager, nach Spektrum) als Plotly-Grafik aus Python (`src/medienmonitor/render.py`)
mit Umschalter und den Schlagzeilen samt Links. Die Felder zeigen die Zahl der
Schlagzeilen (keine Anteile). Der Workflow lädt beide nach
`deutschlandmonitor.info/medienmonitor/`. Die Seite „Medienmonitor“ des deutschlandmonitor
bettet `grafik.html` per iframe ein (Vorlage: `seite/medienmonitor.qmd`);
`plotly.min.js` kommt vom selben Server (`/assets/plotly.min.js`). Ein Thema lässt sich
direkt verlinken: `medienmonitor.html#thema=T5`.

## YouTube-Trends (Branch `youtube`, in Arbeit)

`scripts/run_youtube.py` fragt über die YouTube Data API (Schlüssel `YOUTUBE_API_KEY` in
der Umgebung oder in `.env`) die Uploads der Kanäle aus `youtube.yaml` ab und schreibt
`youtube.json` und `youtube.html`: die 30 meistgesehenen Videos der letzten 10 Tage, die
länger als 10 Minuten sind – ohne Livestreams und Nachrichtensendungen (Titelmuster in
`youtube.py` und je Kanal im Feld `ausschliessen`). Die Grafik zeigt Aufrufe
(logarithmisch) über „Tage online“, darunter die Liste mit Links. Gespeichert wird nur der
aktuelle Stand, keine Historie. Ohne Schlüssel: `--beispiel` (erfundene Videos).

## Stand

- [x] Feeds abrufen und speichern (Duplikate über normalisierte URL)
- [x] Workflow „Abruf“ mit Branch `daten`
- [x] Themenzuordnung per KI (Claude Code mit Abo, Modell Sonnet)
- [x] `daten.json` (24 Stunden, Themen × Mediengruppen, mit Artikellinks)
- [x] Grafik `grafik.html` (je Medium, nach Lager, nach Spektrum)
- [x] Upload per SFTP
- [ ] Seite ins deutschlandmonitor-Repo übernehmen
- [ ] YouTube-Trends (eigener Branch)
- [ ] Podcast (Option)

