import json

import pytest

from game_translator import patching
from game_translator.adapters import scan
from game_translator.models import digest
from game_translator.storage import Project
from test_scan import hashes


@pytest.fixture
def prepared(game, tmp_path):
    project = Project.create(tmp_path / "project", scan(game))
    for segment in project.segments():
        project.save_translation(segment.id, "[SYNTHETIC] " + segment.text, reviewed=True)
    bundle = tmp_path / "output.patch"
    patching.stage(project, bundle)
    project.close()
    return game, bundle, tmp_path / "original.backup"


def test_apply_restore_exact_bytes_and_idempotence(prepared):
    game, bundle, backup = prepared
    original = hashes(game)
    assert patching.apply(game, bundle, backup, approved=True)["state"] == "Applied"
    assert hashes(game) != original
    assert patching.apply(game, bundle, backup, approved=True)["state"] == "AlreadyApplied"
    assert patching.restore(game, backup, approved=True)["state"] == "Restored"
    assert hashes(game) == original
    assert patching.restore(game, backup, approved=True)["files"] == 0


def change_bundle(bundle, mutate):
    path = bundle / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize("evil", ["../outside.json", "data/../../outside.json", "data/evil.js", "C:/evil.json", "data\\Items.json"])
def test_path_traversal_rejected(prepared, evil):
    game, bundle, backup = prepared
    original = hashes(game)
    change_bundle(bundle, lambda m: m["files"][0].update(path=evil))
    with pytest.raises(ValueError):
        patching.apply(game, bundle, backup, approved=True)
    assert hashes(game) == original and not backup.exists()


def test_malicious_rehashed_bundle_cannot_change_script(prepared):
    game, bundle, backup = prepared
    original = hashes(game)
    path = bundle / "files/data/CommonEvents.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[1]["list"][3]["parameters"][0] = "malicious();"
    path.write_text(json.dumps(data), encoding="utf-8")
    change_bundle(bundle, lambda m: next(f for f in m["files"] if f["path"] == "data/CommonEvents.json").update(target_sha256=digest(path.read_bytes())))
    with pytest.raises(ValueError, match="non-translatable"):
        patching.apply(game, bundle, backup, approved=True)
    assert hashes(game) == original


def test_partial_apply_failure_rolls_back(prepared, monkeypatch):
    game, bundle, backup = prepared
    original = hashes(game)
    real_write = patching.write_atomic
    calls = 0
    def fail_second_game_write(path, raw):
        nonlocal calls
        if path.is_relative_to(game):
            calls += 1
            if calls == 2:
                raise OSError("Synthetic disk failure")
        real_write(path, raw)
    monkeypatch.setattr(patching, "write_atomic", fail_second_game_write)
    with pytest.raises(OSError):
        patching.apply(game, bundle, backup, approved=True)
    assert hashes(game) == original


def test_restore_conflict_does_not_overwrite(prepared):
    game, bundle, backup = prepared
    patching.apply(game, bundle, backup, approved=True)
    (game / "data/Items.json").write_text("[]", encoding="utf-8")
    before = hashes(game)
    with pytest.raises(ValueError, match="conflict"):
        patching.restore(game, backup, approved=True)
    assert hashes(game) == before


def test_source_update_rejected_before_backup(prepared):
    game, bundle, backup = prepared
    path = game / "data/Items.json"
    path.write_bytes(path.read_bytes() + b"\n")
    before = hashes(game)
    with pytest.raises(ValueError, match="hash"):
        patching.apply(game, bundle, backup, approved=True)
    assert hashes(game) == before and not backup.exists()


def test_approval_required(prepared):
    game, bundle, backup = prepared
    with pytest.raises(ValueError, match="approval"):
        patching.apply(game, bundle, backup)


def test_rehashed_bad_token_rejected(prepared):
    game, bundle, backup = prepared
    path = bundle / "files/data/CommonEvents.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[1]["list"][0]["parameters"][0] = data[1]["list"][0]["parameters"][0].replace(r"\V[1]", r"\V[2]")
    path.write_text(json.dumps(data), encoding="utf-8")
    change_bundle(bundle, lambda m: next(f for f in m["files"] if f["path"] == "data/CommonEvents.json").update(target_sha256=digest(path.read_bytes())))
    with pytest.raises(ValueError, match="token"):
        patching.apply(game, bundle, backup, approved=True)


def test_corrupted_backup_rejected(prepared):
    game, bundle, backup = prepared
    patching.apply(game, bundle, backup, approved=True)
    path = backup / "files/data/Items.json"
    path.write_bytes(path.read_bytes() + b" ")
    before = hashes(game)
    with pytest.raises(ValueError, match="hash"):
        patching.restore(game, backup, approved=True)
    assert hashes(game) == before


def test_symlink_source_is_never_followed(game, tmp_path):
    path = game / "data/Items.json"
    outside = tmp_path / "outside.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("Creating Windows symlinks requires developer mode or privilege")
    report = scan(game)
    assert not any(s.file == "data/Items.json" for s in report.segments)
    assert any(f.file == "data/Items.json" and f.category == "Warning" for f in report.findings)


def test_crash_prepared_journal_can_restore_on_restart(prepared):
    game, bundle, backup = prepared
    original = hashes(game)
    patching.apply(game, bundle, backup, approved=True)
    journal = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    journal["state"] = "Prepared"
    (backup / "manifest.json").write_text(json.dumps(journal), encoding="utf-8")
    relative = journal["files"][0]["path"]
    (game / relative).write_bytes((backup / "files" / relative).read_bytes())
    patching.restore(game, backup, approved=True)
    assert hashes(game) == original
