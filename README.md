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

## TOP-Themen und Blasen-Themen

Jedes Thema hat ein Ressort (politik, wirtschaft, gesellschaft, wissenschaft, sport,
kultur, panorama), das die KI beim Anlegen vergibt (ältere Themen: `classify_missing`).
`bubbles.py` teilt die Medien in neue (Lager „alternativ“) und alte (alle anderen):

* **TOP-Themen:** in den letzten 24 Stunden mindestens 2 neue und 4 alte Medien.
* **Blasen-Themen:** in den letzten 72 Stunden nur eine Seite (mindestens 2 neue bzw.
  4 alte Medien und 3 Schlagzeilen), nur Ressorts Politik, Wirtschaft, Gesellschaft.

Weil die KI dasselbe Ereignis bei anderer Sichtweise als eigenes Thema anlegen kann,
fragt `cross_check` für jeden Blasen-Kandidaten (höchstens alle 6 Stunden), ob ein Thema
der anderen Seite dasselbe Ereignis beschreibt, und legt beide dann zusammen. Die Frage
nennt keine Seite. Ergebnis: `kategorien` in `daten.json`, Abschnitt unter der Grafik.

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
Schlagzeilen (keine Anteile). In der Ansicht „je Medium“ stehen oben die neuen, unten die
alten Medien, jeweils alphabetisch; der Hover eines Feldes listet seine Schlagzeilen, ein
Klick öffnet sie mit Links, ein Klick auf den Namen oder ein leeres Feld die letzten 10
Schlagzeilen des Mediums (`neueste` in `daten.json`); ↗ hinter dem Namen verlinkt die
Website (`domain` aus `feeds.yaml`). Der Workflow lädt beide nach
`deutschlandmonitor.info/medienmonitor/`. Die Seite „Medienmonitor“ des deutschlandmonitor
bettet `grafik.html` per iframe ein (Vorlage: `seite/medienmonitor.qmd`);
`plotly.min.js` kommt vom selben Server (`/assets/plotly.min.js`). Ein Thema lässt sich
direkt verlinken: `medienmonitor.html#thema=T5`.

## YouTube-Trends

`scripts/run_youtube.py` fragt über die YouTube Data API (Schlüssel `YOUTUBE_API_KEY` in
der Umgebung oder in `.env`) die Uploads der Kanäle aus `youtube.yaml` und deren
Abonnenten ab und schreibt:

* `youtube.json` – je Sprachauswahl (`de`, `en`, `alle`) und Sortierung (`aufrufe`,
  `aufrufe_je_tag`, `aufrufe_erster_tag`) die 50 ersten Videos der letzten 10 Tage, die länger als 8 Minuten sind, höchstens 3 je Kanal; ohne Livestreams
  und Nachrichtensendungen (Titelmuster in `youtube.py` und je Kanal im Feld
  `ausschliessen`), dazu die Kanalliste.
* `youtube.html` – Aufrufe, Aufrufe je Tag oder Aufrufe am ersten Tag (logarithmisch) über
  „Tage online“ und die Top-Liste, mit Umschaltern für Sprache und Sortierung.

„Aufrufe am ersten Tag“ gibt YouTube nicht an: Jeder Lauf merkt sich in
`youtube-zwischenstand.json` (Workflow: Actions-Cache, nicht im Branch `daten`) die
Aufrufe der Videos zuletzt vor und zuerst nach 24 Stunden online; `first_day_views`
interpoliert linear. Einträge fallen nach 11 Tagen heraus (API-Bedingungen: höchstens
30 Tage speichern).
* `kanaele.html` – Kanalübersicht mit demselben Sprach-Umschalter, je Gruppe (staatliche und
  private Medienhäuser; unabhängige Kanäle, Organisationen und neue Medien) eine Tabelle
  mit Abonnenten und Zahl der Videos.

Die Sprache kommt aus `youtube.yaml` (`sprache`: de, en, mehrsprachig); nur bei
mehrsprachigen Kanälen zählt die Sprache des Videos. Gespeichert werden nur der aktuelle
Stand und die Zwischenstände für den ersten Tag, keine Historie. Ohne Schlüssel: `--beispiel` (erfundene Videos). Der Workflow „Abruf“
führt das alle 3 Stunden aus (Secret `YOUTUBE_API_KEY`) und lädt `youtube.html` und
`kanaele.html` mit hoch. Vorlagen für die deutschlandmonitor-Seiten (Menü „Medienmonitor“:
Text-Medien, Video-Medien, YouTube-Kanäle): `seite/medienmonitor.qmd`,
`seite/medienmonitor-video.qmd` und `seite/youtube-kanaele.qmd`.

## Stand

- [x] Feeds abrufen und speichern (Duplikate über normalisierte URL)
- [x] Workflow „Abruf“ mit Branch `daten`
- [x] Themenzuordnung per KI (Claude Code mit Abo, Modell Sonnet)
- [x] `daten.json` (24 Stunden, Themen × Mediengruppen, mit Artikellinks)
- [x] Grafik `grafik.html` (je Medium, nach Lager, nach Spektrum)
- [x] Upload per SFTP
- [x] Seite ins deutschlandmonitor-Repo übernehmen
- [x] YouTube-Trends (alle 3 Stunden)
- [ ] Podcast (Option)

