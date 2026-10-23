import json

import pytest

from game_translator.adapters import DATABASE_FIELDS, read_json, scan
from game_translator.patching import semantic_diff


@pytest.mark.parametrize("name,fields", DATABASE_FIELDS.items())
def test_each_supported_database_schema(game, name, fields):
    path = game / "data" / (name + ".json")
    obj = {field: f"Synthetic {field} İ🌙" for field in fields}
    obj.update(id=1, note="<internal>", meta={"internal": "Do not translate"})
    path.write_text(json.dumps([None, obj], ensure_ascii=False), encoding="utf-8")
    segments = [s for s in scan(game).segments if s.file == "data/" + name + ".json"]
    assert {s.path for s in segments} == {(1, field) for field in fields}


def test_troop_event_commands(game):
    path = game / "data/Troops.json"
    path.write_text(json.dumps([None, {"id": 1, "name": "Internal", "pages": [{"list": [{"code": 401, "indent": 0, "parameters": ["Synthetic battle text"]}]}]}]), encoding="utf-8")
    segments = [s for s in scan(game).segments if s.file == "data/Troops.json"]
    assert [s.text for s in segments] == ["Synthetic battle text"]


def test_unknown_terms_and_invalid_schema_do_not_escape_allowlist(game):
    path = game / "data/System.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["terms"]["unknown_plugin"] = {"script": "Do not translate"}
    path.write_text(json.dumps(data), encoding="utf-8")
    assert not any(s.text == "Do not translate" for s in scan(game).segments)
    data["terms"] = []
    path.write_text(json.dumps(data), encoding="utf-8")
    assert any(f.file == "data/System.json" and f.category == "Warning" for f in scan(game).findings)


@pytest.mark.parametrize("source,target", [([1], [1, 2]), ({"id": 1}, {"id": True}), ({"a": 1}, {"b": 1})])
def test_structural_changes_are_not_text_changes(source, target):
    with pytest.raises(ValueError):
        semantic_diff(source, target)


def test_size_limit_and_bad_unicode(game, monkeypatch):
    import game_translator.adapters as adapters
    path = game / "data/Items.json"
    monkeypatch.setattr(adapters, "MAX_SOURCE_BYTES", 8)
    with pytest.raises(ValueError, match="limit"):
        read_json(path)
    monkeypatch.setattr(adapters, "MAX_SOURCE_BYTES", 1024)
    path.write_bytes(b'[{"name":"\xff"}]')
    assert not any(s.file == "data/Items.json" for s in scan(game).segments)
