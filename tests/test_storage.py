import pytest
import json

from game_translator.adapters import scan
from game_translator.storage import Project
from game_translator.tokens import protect, validate_translation


def test_project_roundtrip_history_and_locks(game, tmp_path):
    report = scan(game)
    directory = tmp_path / "project.gtproj"
    project = Project.create(directory, report)
    segment = report.segments[0]
    translated = segment.text.replace("Welcome", "Hoş geldin")
    project.save_translation(segment.id, translated, reviewed=True, locked=True)
    with pytest.raises(ValueError, match="locked"):
        project.save_translation(segment.id, translated, automatic=True)
    project.save_translation(segment.id, translated + "!", reviewed=True, locked=True)
    project.close()
    reopened = Project(directory)
    assert reopened.translation(segment.id)["text"] == translated + "!"
    assert reopened.progress()["Reviewed"] == 1
    assert reopened.db.execute("SELECT count(*) FROM history").fetchone()[0] == 1
    reopened.close()


@pytest.mark.parametrize("translation", ["", r"Welcome \N[2] \V[2]", r"Welcome \V[1] \N[2]"])
def test_bad_translation_rejected(translation):
    with pytest.raises(ValueError):
        validate_translation(r"Welcome \N[2] \V[1]", translation)


def test_protected_placeholders_roundtrip():
    source = r"Hello \N[2] \V[1] \C[3] \FS[24] %1 {name} <Choice Width: 320>"
    masked = protect(source)
    result = masked.restore(masked.text.replace("Hello", "Merhaba"))
    validate_translation(source, result)
    with pytest.raises(ValueError):
        masked.restore(masked.text.replace("__GT_00000__", "broken"))


def test_project_cannot_live_inside_game(game):
    with pytest.raises(ValueError, match="separate"):
        Project.create(game / "project.gtproj", scan(game))


def test_invalid_imported_manifest_is_not_an_active_project(tmp_path):
    path = tmp_path / "invalid-project"
    path.mkdir()
    (path / "project.json").write_text(json.dumps(["untrusted"]), encoding="utf-8")
    with pytest.raises(ValueError, match="format"):
        Project(path)
