from datetime import UTC, datetime, timedelta

from medienmonitor import publish, store, topics
from medienmonitor.feeds import Headline

NOW = datetime(2026, 11, 24, 12, 17, tzinfo=UTC)


def headline(nr: int, title: str, source: str, camp: str, hours_ago: float = 1) -> Headline:
    moment = (NOW - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    return Headline(
        id=f"h{nr}",
        quelle=source,
        lager=camp,
        spektrum="mitte",
        land="DE",
        titel=title,
        url=f"https://example.org/{nr}",
        veroeffentlicht=moment,
        abgerufen=NOW.isoformat(timespec="seconds"),
    )


class FakeLabeler:
    """Puts every headline containing 'Haushalt' into one new topic, the rest into
    'sonstiges'; records the prompts it gets."""

    def __init__(self, merges=None):
        self.prompts = []
        self.merges = merges or []

    def complete_json(self, system, prompt, schema):
        self.prompts.append(prompt)
        if "zusammenlegungen" in schema["properties"]:
            return {"zusammenlegungen": self.merges}
        lines = prompt.split("Stück:\n", 1)[1].splitlines()
        known = [line.split(" | ")[0] for line in prompt.splitlines() if line.startswith("T")]
        groups: dict[str, list[int]] = {}
        for line in lines:
            nr, title = line.split(" | ", 1)
            ref = (known[0] if known else "neu1") if "Haushalt" in title else topics.OTHER
            groups.setdefault(ref, []).append(int(nr))
        result = {
            "zuordnungen": [{"thema": k, "nummern": v} for k, v in groups.items()],
            "neue_themen": [],
        }
        if not known:
            result["neue_themen"].append(
                {"schluessel": "neu1", "name": "Bundeshaushalt 2027", "beschreibung": "Etat."}
            )
        # invalid entries must be ignored
        result["zuordnungen"].append({"thema": "T1", "nummern": [999]})
        result["zuordnungen"].append({"thema": "T55", "nummern": [1]})
        return result


def fill(tmp_path):
    items = [headline(i, f"Haushalt Meldung {i}", f"Quelle{i % 3}", "links") for i in range(4)]
    items += [headline(10, "Haushalt: Union lehnt ab", "Welt", "rechts")]
    items += [headline(11, "Horoskop für Dienstag", "Bild", "rechts")]
    items += [headline(12, "Haushalt alt", "Welt", "rechts", hours_ago=30)]
    store.append_new(tmp_path, items, NOW)


def test_assign_new_and_payload(tmp_path):
    fill(tmp_path)
    fake = FakeLabeler()
    result = topics.assign_new(tmp_path, fake, NOW)
    assert result == {"offen": 7, "zugeordnet": 7, "fehler": []}
    # the source is never sent to the model
    assert "Welt" not in fake.prompts[0] and "Quelle1" not in fake.prompts[0]
    rows = {r["id"]: r for r in store.read_day(tmp_path, NOW.date())}
    assert rows["h0"]["thema_id"] == "T1" and rows["h11"]["thema_id"] == topics.OTHER
    assert topics.assign_new(tmp_path, fake, NOW)["offen"] == 0

    payload = publish.build_payload(tmp_path, NOW)
    assert payload["artikel_gesamt"] == 6  # h12 is older than 24 h
    [topic] = payload["themen"]
    assert topic["name"] == "Bundeshaushalt 2027" and topic["anzahl_gesamt"] == 5
    assert topic["anzahl"]["lager"] == {"links": 4, "rechts": 1}
    assert topic["anteil_pct"]["lager"]["links"] == 100.0
    assert topic["anteil_pct"]["lager"]["rechts"] == 50.0  # 1 of 2 right-camp articles
    assert topic["artikel"][0]["url"].startswith("https://")


def test_second_run_reuses_topic(tmp_path):
    fill(tmp_path)
    topics.assign_new(tmp_path, FakeLabeler(), NOW)
    store.append_new(tmp_path, [headline(20, "Haushalt beschlossen", "taz", "links")], NOW)
    fake = FakeLabeler()
    topics.assign_new(tmp_path, fake, NOW)
    assert "T1 | Bundeshaushalt 2027" in fake.prompts[0]
    assert store.read_day(tmp_path, NOW.date())[-1]["thema_id"] == "T1"
    assert topics.TopicList.load(tmp_path).naechste_nr == 2


def test_merge_and_resolve(tmp_path):
    topic_list = topics.TopicList()
    a = topic_list.add("Haushalt 2027", "x", NOW)
    b = topic_list.add("Bundesetat 2027", "x", NOW)
    c = topic_list.add("Bahnstreik", "x", NOW)
    assert topic_list.merge([b], a, "Bundeshaushalt 2027") == 1
    assert topic_list.resolve(b) == a and topic_list.resolve(c) == c
    assert topic_list.themen[a]["name"] == "Bundeshaushalt 2027"
    assert topic_list.active(NOW) == [a, c] or set(topic_list.active(NOW)) == {a, c}
    assert topic_list.resolve(topics.OTHER) == topics.OTHER


def test_consolidate_ignores_unknown_ids(tmp_path):
    topic_list = topics.TopicList()
    a = topic_list.add("Haushalt 2027", "x", NOW)
    b = topic_list.add("Bundesetat 2027", "x", NOW)
    topic_list.save(tmp_path)
    merges = [{"von": [b, "T99"], "nach": a}, {"von": [a], "nach": "T77"}]
    assert topics.consolidate(tmp_path, FakeLabeler(merges), NOW)["zusammengelegt"] == 1
    assert topics.TopicList.load(tmp_path).resolve(b) == a


def test_labeler_failure_keeps_headlines_open(tmp_path):
    class Broken:
        def complete_json(self, *args):
            raise RuntimeError("Limit erreicht")

    fill(tmp_path)
    result = topics.assign_new(tmp_path, Broken(), NOW)
    assert result["zugeordnet"] == 0 and result["fehler"] == ["Limit erreicht"]
    assert all(not r.get("thema_id") for r in store.read_day(tmp_path, NOW.date()))
