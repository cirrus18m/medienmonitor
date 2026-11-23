# Medienmonitor

Sammelt stündlich die Schlagzeilen deutschsprachiger Medien (RSS-Feeds aus
[feeds.yaml](feeds.yaml)), ordnet sie per KI Themen zu und bereitet für die Seite
„Medienmonitor“ auf deutschlandmonitor.info auf, welche Mediengruppen über welche Themen
berichten.

Gespeichert werden nur Überschrift, Link, Quelle und Zeit, keine Artikeltexte.

## Befehle

```bash
uv sync                                  # Umgebung
uv run scripts/check_feeds.py            # alle Feeds prüfen
uv run scripts/run_hourly.py             # abrufen, neue Titel nach daten/titel/JJJJ/MM/TT.jsonl
uv run pytest && uv run ruff check .
```

## Stand

- [x] Feeds abrufen und speichern (Duplikate über normalisierte URL)
- [ ] Workflow „Abruf“ mit Branch `daten`
- [ ] Themenzuordnung per KI
- [ ] `daten.json` und Upload per SFTP
- [ ] Podcast (Option)
