from datetime import UTC, datetime, timedelta

from medienmonitor import bubbles, render, topics

NOW = datetime(2026, 11, 24, 12, 17, tzinfo=UTC)


def row(nr: int, topic: str, source: str, new: bool, hours_ago: float = 1) -> dict:
    moment = (NOW - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    return {
        "id": f"h{nr}",
        "quelle": source,
        "lager": "alternativ" if new else "mitte",
        "spektrum": "mitte",
        "titel": f"Schlagzeile {nr}",
        "url": f"https://example.org/{nr}",
        "veroeffentlicht": moment,
        "abgerufen": NOW.isoformat(timespec="seconds"),
        "thema_id": topic,
    }


def make_topics() -> topics.TopicList:
    result = topics.TopicList()
    result.add("Haushalt 2027", "Etat.", NOW, "politik")  # T1: both sides
    result.add("Statistik Sozialleistungen", "x", NOW, "gesellschaft")  # T2: new only
    result.add("Drohnen über Polen", "x", NOW, "politik")  # T3: old only, 2 days ago
    result.add("Champions League", "x", NOW, "sport")  # T4: old only, but sport
    result.add("Sozialleistungen Ausländer", "x", NOW, "gesellschaft")  # T5: twin of T2
    return result


def rows() -> list[dict]:
    old = ["Spiegel", "Zeit", "FAZ", "taz"]
    result = [row(i, "T1", name, False) for i, name in enumerate(old)]
    result += [row(10, "T1", "NIUS", True), row(11, "T1", "Compact", True)]
    result += [row(20, "T2", "NIUS", True), row(21, "T2", "Compact", True)]
    result += [row(22, "T2", "Apollo News", True)]
    result += [row(30 + i, "T3", name, False, hours_ago=48) for i, name in enumerate(old)]
    result += [row(40 + i, "T4", name, False) for i, name in enumerate(old)]
    result += [row(50, "T5", "Welt", False, hours_ago=80)]  # outside the window
    result += [row(60, topics.OTHER, "Bild", False)]
    return result


def test_categories():
    result = bubbles.categories(rows(), make_topics(), NOW)
    assert [e["id"] for e in result["top"]] == ["T1"]
    assert result["top"][0]["neu"] == {"artikel": 2, "medien": 2}
    assert result["top"][0]["alt"] == {"artikel": 4, "medien": 4}
    assert [e["id"] for e in result["blase_neu"]] == ["T2"]
    assert [e["id"] for e in result["blase_alt"]] == ["T3"]  # T4 is sport
    assert result["blase_neu"][0]["artikel"][0]["url"] == "https://example.org/20"


class Twins:
    """Answers that T2 is the same as T1 and records the prompts."""

    def __init__(self, twin="T1"):
        self.prompts = []
        self.twin = twin

    def complete_json(self, system, prompt, schema):
        self.prompts.append(prompt)
        return {"treffer": [{"thema": "T2", "gleich": self.twin}, {"thema": "T9", "gleich": "T1"}]}


def test_cross_check_merges_twins_and_names_no_side():
    topic_list = make_topics()
    model = Twins()
    result = bubbles.cross_check(topic_list, rows(), model, NOW)
    assert result == {"geprueft": 2, "zusammengelegt": 1, "fehler": []}
    assert topic_list.resolve("T2") == "T1"
    new_prompt = next(p for p in model.prompts if p.startswith("Liste A") and "T2 |" in p)
    assert "NIUS" not in new_prompt and "alternativ" not in new_prompt
    assert "T1 | Haushalt 2027" in new_prompt.split("Liste B", 1)[1]
    after = bubbles.categories(rows(), topic_list, NOW)
    assert after["blase_neu"] == []
    # checked candidates wait RECHECK_HOURS before the next question
    assert bubbles.cross_check(topic_list, rows(), Twins(), NOW)["geprueft"] == 0


def test_cross_check_ignores_unknown_ids_and_keeps_failures_open():
    topic_list = make_topics()
    assert bubbles.cross_check(topic_list, rows(), Twins("T99"), NOW)["zusammengelegt"] == 0

    class Broken:
        def complete_json(self, *args):
            raise RuntimeError("Limit erreicht")

    fresh = make_topics()
    result = bubbles.cross_check(fresh, rows(), Broken(), NOW)
    assert result["fehler"] == ["Limit erreicht", "Limit erreicht"]
    assert "gegengeprueft" not in fresh.themen["T2"]


def test_classify_missing():
    topic_list = topics.TopicList()
    topic_list.add("Bahnstreik", "x", NOW)
    topic_list.add("Bundesliga", "x", NOW, "sport")

    class Model:
        def complete_json(self, system, prompt, schema):
            assert "T2" not in prompt
            return {"ressorts": [{"thema": "T1", "ressort": "wirtschaft"}]}

    assert topics.classify_missing(topic_list, Model(), NOW) == {
        "offen": 1,
        "eingeordnet": 1,
        "fehler": [],
    }
    assert topic_list.themen["T1"]["ressort"] == "wirtschaft"


def test_new_topic_gets_ressort():
    topic_list = topics.TopicList()
    answer = {
        "zuordnungen": [{"thema": "neu1", "nummern": [1]}],
        "neue_themen": [
            {
                "schluessel": "neu1",
                "name": "Bahnstreik",
                "beschreibung": "x",
                "ressort": "wirtschaft",
            }
        ],
    }
    topics.apply_assignment(topic_list, answer, [{"id": "a"}], [], NOW)
    assert topic_list.themen["T1"]["ressort"] == "wirtschaft"


def test_render_shows_categories():
    payload = {
        "stand": "2026-11-24T13:17+01:00",
        "fenster_stunden": 24,
        "gruppen": {"lager": ["mitte"], "spektrum": ["mitte"]},
        "artikel_je_gruppe": {"lager": {"mitte": 1}, "spektrum": {"mitte": 1}},
        "artikel_gesamt": 1,
        "quellen_gesamt": 1,
        "medien": [],
        "themen": [],
        "kategorien": bubbles.categories(rows(), make_topics(), NOW),
    }
    html = render.render_html(payload)
    assert '"blase_neu":[{"id":"T2"' in html and "TOP-Themen und Blasen-Themen" in html
