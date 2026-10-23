import copy
import json
import os
import re
import uuid
from pathlib import Path

from . import __version__
from .adapters import detect_game, parse_json, read_json, safe_path, source_bytes
from .models import digest
from .storage import now
from .tokens import validate_translation


def outside_game(directory: Path, game: Path):
    directory = directory.absolute()
    if directory.resolve().is_relative_to(game.resolve()) or game.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Patch/backup directories must be separate from the game")
    if any(p.is_symlink() or p.is_junction() for p in (directory, *directory.parents)):
        raise ValueError("Symlink/junction output directories are unsupported")
    return directory


def allowed_file(relative):
    return bool(re.fullmatch(r"data/(?:Map\d+|CommonEvents|System|Actors|Classes|Items|Weapons|Armors|Skills|States|Enemies|Troops)\.json", relative))


def semantic_diff(source, target, path=()):
    if type(source) is not type(target):
        raise ValueError("JSON type changed")
    if isinstance(source, dict):
        if source.keys() != target.keys():
            raise ValueError("JSON object keys changed")
        result = []
        for key in source:
            result.extend(semantic_diff(source[key], target[key], path + (key,)))
        return result
    if isinstance(source, list):
        if len(source) != len(target):
            raise ValueError("JSON array length changed")
        result = []
        for index, (before, after) in enumerate(zip(source, target)):
            result.extend(semantic_diff(before, after, path + (index,)))
        return result
    return [(path, source, target)] if source != target else []


def validate_patch(adapter, relative, source, target):
    if not allowed_file(relative):
        raise ValueError("Patch file type is not permitted")
    segments, _, _ = adapter.extract(relative, source)
    allowed = {segment.path: segment for segment in segments}
    changes = semantic_diff(source, target)
    for path, before, after in changes:
        if path not in allowed or not isinstance(before, str) or not isinstance(after, str):
            raise ValueError("Patch changes a non-translatable field")
        validate_translation(before, after)
    return [{"path": list(path), "before": before, "after": after} for path, before, after in changes]


def write_atomic(path, raw):
    temporary = path.with_name(path.name + ".gt-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_journal(directory, manifest):
    write_atomic(directory / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))


def stage(project, directory: Path):
    root, adapter = detect_game(Path(project.manifest["game"]))
    if adapter.engine != project.manifest["engine"]:
        raise ValueError("Project engine no longer matches source")
    directory = outside_game(directory, root)
    if directory.exists():
        raise ValueError("Staging directory already exists; choose a new directory")
    by_file = {}
    for segment in project.segments():
        entry = project.translation(segment.id)
        if entry and entry["status"] == "Reviewed":
            by_file.setdefault(segment.file, []).append((segment, entry["text"]))
    sources = dict(project.db.execute("SELECT path,sha256 FROM sources"))
    prepared = []
    for relative, translations in by_file.items():
        if not allowed_file(relative):
            raise ValueError("Project references unsupported source")
        source_path = safe_path(root, relative)
        original = source_bytes(source_path)
        if digest(original) != sources.get(relative):
            raise ValueError("Source hash mismatch; rescan the updated game")
        source = parse_json(original)
        eligible = {s.id: s for s in adapter.extract(relative, source)[0]}
        target = copy.deepcopy(source)
        for segment, text in translations:
            if segment.id not in eligible or eligible[segment.id] != segment:
                raise ValueError("Project segment differs from current source")
            validate_translation(segment.text, text)
            parent = target
            for part in segment.path[:-1]:
                parent = parent[part]
            parent[segment.path[-1]] = text
        changes = validate_patch(adapter, relative, source, target)
        if changes:
            raw = json.dumps(target, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
            prepared.append((relative, original, raw, changes))
    if not prepared:
        raise ValueError("No reviewed changes to stage")
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"format": 1, "id": str(uuid.uuid4()), "engine": adapter.engine,
                "target_language": project.target, "created": now(), "app_version": __version__, "files": []}
    for relative, original, raw, changes in prepared:
        output = safe_path(directory, "files/" + relative)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        manifest["files"].append({"path": relative, "source_sha256": digest(original),
                                  "target_sha256": digest(raw), "changes": changes})
    save_journal(directory, manifest)
    return manifest


def load_manifest(directory):
    manifest = read_json(safe_path(directory, "manifest.json"))
    if not isinstance(manifest, dict) or manifest.get("format") != 1 or manifest.get("engine") not in ("MV", "MZ"):
        raise ValueError("Unsupported patch manifest")
    files = manifest.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 10000:
        raise ValueError("Invalid patch file list")
    seen = set()
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not allowed_file(item["path"]):
            raise ValueError("Unsafe patch file path/type")
        relative = item["path"]
        if relative.casefold() in seen:
            raise ValueError("Duplicate patch path")
        seen.add(relative.casefold())
        for key in ("source_sha256", "target_sha256"):
            if not isinstance(item.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", item[key]):
                raise ValueError("Invalid SHA-256")
    return manifest


def apply(game: Path, bundle: Path, backup: Path, approved=False):
    if not approved:
        raise ValueError("Explicit patch approval is required")
    root, adapter = detect_game(game)
    bundle, backup = outside_game(bundle, root), outside_game(backup, root)
    if backup.resolve().is_relative_to(bundle.resolve()) or bundle.resolve().is_relative_to(backup.resolve()):
        raise ValueError("Patch and backup must be separate")
    manifest = load_manifest(bundle)
    if manifest["engine"] != adapter.engine:
        raise ValueError("Patch engine mismatch")
    if backup.exists():
        journal = load_manifest(backup)
        if journal.get("patch_id") == manifest.get("id") and journal.get("state") == "Applied" and all(
            digest(safe_path(root, f["path"]).read_bytes()) == f["target_sha256"] for f in journal["files"]):
            return {"state": "AlreadyApplied", "backup": str(backup)}
        raise ValueError("Backup directory already exists; inspect/restore it first")
    prepared = []
    for item in manifest["files"]:
        relative = item["path"]
        path = safe_path(root, relative)
        original = source_bytes(path)
        if digest(original) != item["source_sha256"]:
            raise ValueError("Source hash mismatch; no files written")
        staged = safe_path(bundle, "files/" + relative)
        raw = source_bytes(staged)
        target = parse_json(raw)
        if digest(raw) != item["target_sha256"]:
            raise ValueError("Staged hash mismatch")
        validate_patch(adapter, relative, parse_json(original), target)
        prepared.append((relative, original, raw))
    backup.mkdir(parents=True, exist_ok=False)
    journal = {"format": 1, "engine": adapter.engine, "patch_id": manifest.get("id"),
               "game": str(root.resolve()), "state": "Preparing", "created": now(), "files": manifest["files"]}
    for relative, original, _ in prepared:
        path = safe_path(backup, "files/" + relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)
        if digest(path.read_bytes()) != digest(original):
            raise ValueError("Backup verification failed; game untouched")
    journal["state"] = "Prepared"
    save_journal(backup, journal)
    try:
        for relative, original, raw in prepared:
            path = safe_path(root, relative)
            if digest(path.read_bytes()) != digest(original):
                raise ValueError("Source changed during apply")
            write_atomic(path, raw)
            if digest(path.read_bytes()) != digest(raw):
                raise ValueError("Applied hash verification failed")
        journal["state"] = "Applied"
        save_journal(backup, journal)
    except BaseException:
        # Persistent Prepared journal also permits recovery after process/power loss.
        try:
            restore(root, backup, approved=True)
        except BaseException:
            journal["state"] = "RecoveryRequired"
            save_journal(backup, journal)
        raise
    return {"state": "Applied", "backup": str(backup), "files": len(prepared)}


def restore(game: Path, backup: Path, approved=False):
    if not approved:
        raise ValueError("Explicit restore approval is required")
    root, adapter = detect_game(game)
    backup = outside_game(backup, root)
    journal = load_manifest(backup)
    if journal["engine"] != adapter.engine or journal.get("game") != str(root.resolve()):
        raise ValueError("Backup belongs to a different game")
    prepared = []
    for item in journal["files"]:
        path = safe_path(root, item["path"])
        current = source_bytes(path)
        original_path = safe_path(backup, "files/" + item["path"])
        original = source_bytes(original_path)
        original_data = parse_json(original)
        if digest(original) != item["source_sha256"]:
            raise ValueError("Backup hash mismatch")
        if digest(current) not in (item["source_sha256"], item["target_sha256"]):
            raise ValueError("Restore conflict: file changed after apply; no files written")
        validate_patch(adapter, item["path"], original_data, parse_json(current))
        if current != original:
            prepared.append((path, original, digest(current)))
    journal["state"] = "Restoring"
    save_journal(backup, journal)
    for path, original, expected_hash in prepared:
        if digest(path.read_bytes()) != expected_hash:
            raise ValueError("Restore conflict during write; retry after inspection")
        write_atomic(path, original)
        if digest(path.read_bytes()) != digest(original):
            raise ValueError("Restore verification failed")
    journal["state"] = "Restored"
    save_journal(backup, journal)
    return {"state": "Restored", "files": len(prepared)}
