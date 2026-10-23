import json


def test_fixture_is_synthetic_valid_json(game):
    commands = json.loads((game / "data/CommonEvents.json").read_text(encoding="utf-8"))[1]["list"]
    assert len(commands[0]["parameters"]) == 1
    assert [c["code"] for c in commands] == [401, 102, 405, 355, 655, 357]
    assert "setValue(21" in commands[3]["parameters"][0]
