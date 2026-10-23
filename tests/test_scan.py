import json

import pytest

from game_translator.adapters import scan
from game_translator.models import digest


def hashes(game):
    return {p.relative_to(game).as_posix(): digest(p.read_bytes()) for p in game.rglob("*") if p.is_file()}


def test_read_only_golden_extraction(game):
    before = hashes(game)
    report = scan(game)
    assert hashes(game) == before
    assert report.engine == "MZ"
    assert len(report.segments) == 17  # 4 common + 5 map + 2 item + 6 system strings
    assert {s.path for s in report.segments if s.file == "data/CommonEvents.json"} == {
        (1, "list", 0, "parameters", 0), (1, "list", 1, "parameters", 0, 0),
        (1, "list", 1, "parameters", 0, 1), (1, "list", 2, "parameters", 0),
    }
    texts = {s.text for s in report.segments}
    assert {"Potion", "Enter", "Leave", "Moon Village", "%1 won!"} <= texts
    assert not any("setValue" in s.text or "Internal" in s.text or "img/" in s.text or "Plugin text" in s.text for s in report.segments)
    assert any("355" in f.reason for f in report.findings)
    assert any("655" in f.reason for f in report.findings)
    assert any("357" in f.reason for f in report.findings)
    assert [s.id for s in scan(game).segments] == [s.id for s in report.segments]


def test_invalid_json_is_reported(game):
    (game / "data/Items.json").write_text('{"broken":', encoding="utf-8")
    report = scan(game)
    assert any(f.file == "data/Items.json" and f.category == "Warning" for f in report.findings)


@pytest.mark.parametrize("content", ['{"a":1,"a":2}', '[NaN]', '[{"name": 42}]'])
def test_bad_source_schema_is_rejected(game, content):
    (game / "data/Items.json").write_text(content, encoding="utf-8")
    assert not any(s.file == "data/Items.json" for s in scan(game).segments)


def test_unknown_engine_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        scan(tmp_path)


def test_unicode_and_array_shape(game):
    path = game / "data/CommonEvents.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[1]["list"][0]["parameters"] = ["İğüşöç 日本語 🌙"]
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert any(s.text == "İğüşöç 日本語 🌙" for s in scan(game).segments)
    assert len(json.loads(path.read_text(encoding="utf-8"))[1]["list"][0]["parameters"]) == 1
