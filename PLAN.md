# Ausbauplan Medienmonitor

Stand: 24.11.2026. Umgesetzt ist der stündliche Abruf der Schlagzeilen, die Zuordnung zu
Themen per KI und `daten.json` (siehe README, Abschnitt „Stand“).

## 1. Seite und Upload

- Upload von `daten.json` per SFTP nach `deutschlandmonitor.info/medienmonitor/` (Workflow
  „Abruf“, Schritt „daten.json hochladen“, mit zwei Marken-Dateien als Schutz).
- Seite „Medienmonitor“ im deutschlandmonitor-Repo: `site/medienmonitor.qmd`,
  `site/assets/medienmonitor.js` (Vorlagen in `seite/`), Eintrag in `navigation.py`,
  `--exclude-glob medienmonitor/` im Website-Workflow, Abschnitt in der
  Datenschutzerklärung.
- Ansichten: „je Medium“ (neue Medien oben, etablierte unten, jeweils von links nach
  rechts nach `spektrum`), „nach Lager“, „nach Spektrum“. Die Einordnung kommt vorerst aus
  `feeds.yaml`.

## 2. YouTube-Trends

Ziel: zeigen, welche politischen Videos deutschsprachiger Kanäle gerade die meisten
Aufrufe haben, und wie alt sie sind.

**Kanalliste** `youtube.yaml` (wie `feeds.yaml`): `name`, `kanal_id` (`UC…`), `land`,
`lager`, `spektrum`, `art` (unabhängig, Medienhaus, Politik/Partei), `aktiv`. Vorschlag
für den Start siehe unten; Kanal-IDs und Einordnung vor dem ersten Lauf prüfen.

**Abruf** (eigener Schritt im Workflow, alle 3 Stunden genügt):
1. Je Kanal der öffentliche Kanal-Feed
   `https://www.youtube.com/feeds/videos.xml?channel_id=<kanal_id>`: die letzten 15
   Videos mit Titel, Link, Veröffentlichung und Aufrufzahl (`media:statistics views`).
   Ohne Schlüssel und ohne Kontingent.
2. Optional genauer: YouTube Data API v3 `videos.list` (`part=statistics,contentDetails`,
   bis 50 Videos je Abfrage = 1 Einheit; frei sind 10.000 Einheiten am Tag). Braucht ein
   Secret `YOUTUBE_API_KEY`. Liefert auch die Dauer, damit sich Shorts (≤ 60 s bzw. 3 min)
   getrennt zeigen oder ausblenden lassen. Die Aufrufzahl im Feed wird von YouTube nur
   verzögert aktualisiert; reicht sie nicht, auf die API umstellen.
3. Speicherung im Branch `daten`: `youtube/JJJJ/MM/TT.jsonl`, je Abruf eine Zeile je Video
   mit `video_id`, `kanal`, `titel`, `veroeffentlicht`, `aufrufe`, `abgerufen`. So lässt
   sich später auch die Zunahme der Aufrufe zeigen.

**Ausgabe** `youtube.json` (Upload wie `daten.json`):
- Videos der letzten **10 Tage**, die **30** mit den meisten Aufrufen.
- Je Video: Titel, Kanal, Lager, Spektrum, veröffentlicht, Tage online, Aufrufe, Link.

**Darstellung** auf der Seite „Medienmonitor“ (Abschnitt „YouTube“):
- Streudiagramm: x = „Tage online“ (0–10), y = „Aufrufe“ (logarithmisch), Farbe nach Lager
  (neue Medien / etablierte Medien, wie oben), Hover mit Titel, Kanal und Aufrufen; Klick
  zeigt das Video in der Liste.
- Darunter die Top-30-Liste mit Rang, Kanal, Titel (Link zu YouTube), Aufrufe, Alter.
- Hinweis: Ältere Videos hatten mehr Zeit, Aufrufe zu sammeln; zusätzlich Aufrufe je Tag
  online als Spalte.
- **Keine eingebetteten Videos und keine Vorschaubilder von YouTube-Servern**: Die Seite
  lädt dann nichts von Google, die Datenschutzerklärung bleibt einfach. Links öffnen
  YouTube erst auf Klick.

**Später:** Videotitel mit demselben KI-Schritt den Themen zuordnen; dann bekommt die
Ansicht „je Medium“ auch Zeilen für YouTube-Kanäle, und der Podcast kann sagen, welche
Themen auf YouTube größer sind als in den Schlagzeilen.

**Rechtliches:** Gespeichert und gezeigt werden nur Titel, Kanal, Aufrufzahl und Link. Die
Nutzung der Data API unterliegt den YouTube API Services Terms (u. a. Daten höchstens 30
Tage zwischenspeichern, wenn sie nicht aktualisiert werden); vor dem Einsatz der API
prüfen. Der Kanal-Feed ist öffentlich und frei abrufbar.

### Vorschlag Kanalliste (zu prüfen)

Einordnung nach derselben Regel wie in `feeds.yaml`: etablierte Medienhäuser nach
Spektrum, unabhängige Kanäle mit Haltung gegen etablierte Medien als `alternativ`.

| Kanal | Art | lager | spektrum |
| --- | --- | --- | --- |
| tagesschau | Medienhaus | mitte | mitte |
| ZDFheute Nachrichten | Medienhaus | mitte | mitte |
| phoenix | Medienhaus | mitte | mitte |
| DER SPIEGEL | Medienhaus | links | mitte-links |
| WELT Nachrichtensender | Medienhaus | rechts | mitte-rechts |
| BILD | Medienhaus | rechts | mitte-rechts |
| MrWissen2go (funk) | unabhängig, öffentlich-rechtlich finanziert | mitte | mitte |
| Die Da Oben! (funk) | unabhängig, öffentlich-rechtlich finanziert | links | mitte-links |
| Simplicissimus | unabhängig | mitte | mitte |
| Rezo | unabhängig | links | mitte-links |
| Jung & Naiv (Tilo Jung) | unabhängig | links | links |
| Wohlstand für Alle (Nymoen/Schmitt) | unabhängig | links | links |
| NachDenkSeiten | unabhängig | alternativ | links |
| acTVism Munich | unabhängig | alternativ | links |
| NIUS | unabhängig | alternativ | rechts |
| Tichys Einblick | unabhängig | alternativ | rechts |
| Apollo News | unabhängig | alternativ | rechts |
| Reitschuster | unabhängig | alternativ | rechts |
| Punkt.PRERADOVIC | unabhängig | alternativ | rechts |
| Hallo Meinung | unabhängig | alternativ | rechts |
| Clownswelt | unabhängig | alternativ | rechts |
| Weltwoche Daily | unabhängig (CH) | alternativ | rechts |
| Kettner Edelmetalle | Grenzfall: Finanzen, viel Politik | alternativ | rechts |
| Hoss & Hopf | Grenzfall: Podcast, Wirtschaft/Politik | alternativ | unklar |
| Daniele Ganser | unabhängig (CH) | alternativ | unklar |
| AfD-Fraktion im Bundestag | Politik/Partei | – | rechts |
| Sahra Wagenknecht | Politik/Partei | – | unklar |

Parteien und Politiker getrennt führen (`art: Politik/Partei`), damit sie die Mediengruppen
nicht verzerren; ob sie überhaupt in die Top 30 sollen, entscheidet ein Schalter.
AUF1, Compact und apolut sind auf YouTube nicht mehr (oder nur eingeschränkt) vertreten –
prüfen und sonst weglassen.

## 3. Podcast (Option)

Täglich, Skript per KI aus den eigenen Themen, Sprachausgabe lokal mit Piper; nur frei
nutzbare Hintergrundquellen (keine dpa- und keine X-Inhalte). Details im ursprünglichen
Plan (Abschnitt 6): Themenauswahl, Skript als Dialog, Kennzeichnung „KI-Stimme“, MP3 und
Podcast-Feed in `medienmonitor/podcast/`.
