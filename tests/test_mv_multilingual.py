import json

import pytest

from conftest import make_game
from game_translator.adapters import detect_game, scan
from game_translator.patching import apply, restore, stage
from game_translator.storage import Project
from test_scan import hashes


@pytest.fixture
def mv_game(tmp_path):
    game = make_game(tmp_path / "mv" / "www", engine="MV")
    path = game / "data/CommonEvents.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[1]["list"].append({"code": 101, "indent": 0, "parameters": ["ActorFace", 0, 0, 2]})
    data[1]["list"].append({"code": 356, "indent": 0, "parameters": ["TextPicture set Synthetic plugin text"]})
    path.write_text(json.dumps(data), encoding="utf-8")
    return game


def test_mv_independent_golden_fixture(mv_game):
    before = hashes(mv_game)
    report = scan(mv_game.parent)
    assert report.engine == "MV" and len(report.segments) == 17
    assert not any(s.text == "ActorFace" or "setValue" in s.text for s in report.segments)
    assert any("356" in f.reason for f in report.findings)
    assert hashes(mv_game) == before


def test_mv_patch_restore_and_mz_incompatibility(mv_game, game, tmp_path):
    before = hashes(mv_game)
    project = Project.create(tmp_path / "mv-project", scan(mv_game.parent))
    segment = next(s for s in project.segments() if s.text == "Potion")
    project.save_translation(segment.id, "İksir", reviewed=True)
    bundle, backup = tmp_path / "mv.patch", tmp_path / "mv.backup"
    stage(project, bundle)
    with pytest.raises(ValueError, match="engine"):
        apply(game, bundle, backup, approved=True)
    apply(mv_game.parent, bundle, backup, approved=True)
    restore(mv_game.parent, backup, approved=True)
    assert hashes(mv_game) == before
    project.close()


def test_mz_speaker_field_and_ambiguous_markers(game):
    path = game / "data/CommonEvents.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[1]["list"].append({"code": 101, "indent": 0, "parameters": ["ActorFace", 0, 0, 2, "Visible Speaker"]})
    path.write_text(json.dumps(data), encoding="utf-8")
    assert any(s.text == "Visible Speaker" for s in scan(game).segments)
    (game / "js/rpg_core.js").write_text("// Synthetic MV marker", encoding="utf-8")
    with pytest.raises(ValueError, match="Ambiguous"):
        detect_game(game)


def test_targets_translation_memory_glossary_and_jobs_are_isolated(game, tmp_path):
    project = Project.create(tmp_path / "project", scan(game))
    segment = next(s for s in project.segments() if s.text == "Potion")
    project.set_glossary("Potion", "İksir")
    project.save_translation(segment.id, "İksir", reviewed=True)
    project.set_target("DE")
    assert project.translation(segment.id) is None
    assert project.recalled(segment) is None and project.glossary() == {}
    project.save_translation(segment.id, "Trank", reviewed=True)
    project.close()
    project = Project(tmp_path / "project")
    assert project.target == "DE" and project.translation(segment.id)["text"] == "Trank"
    project.set_target("TR")
    assert project.translation(segment.id)["text"] == "İksir"
    assert project.recalled(segment) == "İksir"
    project.close()
