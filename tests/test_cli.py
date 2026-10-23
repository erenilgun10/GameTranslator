import json
import os
import subprocess
import sys

from game_translator.cli import main
from game_translator.adapters import scan
from game_translator.storage import Project


def test_corrupt_database_reports_error_without_traceback(game, tmp_path):
    project = Project.create(tmp_path / "corrupt-project", scan(game))
    project.close()
    (project.directory / "project.sqlite3").write_bytes(b"not a SQLite database")
    result = subprocess.run([sys.executable, "-m", "game_translator", "status", str(project.directory)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr


def test_missing_project_language_reports_error_without_traceback(game, tmp_path):
    project = Project.create(tmp_path / "bad-manifest", scan(game))
    project.close()
    manifest = project.manifest
    del manifest["target_language"]
    (project.directory / "project.json").write_text(json.dumps(manifest), encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "game_translator", "status", str(project.directory)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr


def test_scan_cli(game, capsys):
    main(["scan", str(game)])
    report = json.loads(capsys.readouterr().out)
    assert report["engine"] == "MZ"
    assert report["counts"]["Extracted"] == 17
    assert report["counts"]["Translated"] == 0 and report["counts"]["Reviewed"] == 0


def test_redirected_windows_codepage_does_not_break_unicode(game):
    path = game / "data/Items.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[1]["name"] = "İksir 🌙"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="cp1254")
    result = subprocess.run([sys.executable, "-m", "game_translator", "scan", str(game)], env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stderr
    assert any(s["text"] == "İksir 🌙" for s in json.loads(result.stdout)["segments"])
