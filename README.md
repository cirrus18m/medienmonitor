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
uv run scripts/run_hourly.py             # abrufen, Themen zuordnen, daten/daten.json schreiben
uv run scripts/run_hourly.py --no-topics # nur abrufen (ohne KI)
uv run scripts/preview.py --data-dir daten --plotly <pfad>/plotly.min.js  # Seite lokal ansehen
uv run pytest && uv run ruff check .
```

## Seite

`seite/medienmonitor.js` und `seite/medienmonitor.qmd` sind die Vorlagen für die Seite
„Medienmonitor“ im deutschlandmonitor-Repo (`site/assets/medienmonitor.js`,
`site/medienmonitor.qmd`). Das Skript lädt `medienmonitor/daten.json` vom eigenen Server
und zeigt die Themen als Heatmap (Lager oder Spektrum) mit Artikellinks. Ein Thema lässt
sich direkt verlinken: `medienmonitor.html#thema=T5`.

## Stand

- [x] Feeds abrufen und speichern (Duplikate über normalisierte URL)
- [x] Workflow „Abruf“ mit Branch `daten`
- [x] Themenzuordnung per KI (Claude Code mit Abo, Modell Sonnet)
- [x] `daten.json` (24 Stunden, Themen × Mediengruppen, mit Artikellinks)
- [x] Seite als Prototyp (`seite/`)
- [ ] Seite ins deutschlandmonitor-Repo übernehmen
- [ ] Upload per SFTP
- [ ] Podcast (Option)
