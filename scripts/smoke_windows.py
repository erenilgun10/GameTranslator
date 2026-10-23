"""Exercise a frozen Windows package using synthetic data in a temporary folder."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    package = args.package.resolve()
    cli = package / "GameTranslator-CLI.exe"
    def run(*arguments):
        result = subprocess.run([str(cli), *map(str, arguments)], capture_output=True, text=True, encoding="utf-8", timeout=60)
        if result.returncode:
            raise RuntimeError(f"Frozen CLI failed: {result.stderr}")
        return result.stdout
    print("Frozen CLI version:", run("--version").strip())
    subprocess.run([str(package / "GameTranslator.exe"), "--smoke-test"], check=True, timeout=30)
    with tempfile.TemporaryDirectory(prefix="game-translator-smoke-") as temporary:
        base = Path(temporary)
        game = base / "synthetic-mz"
        shutil.copytree(package / "examples/synthetic-mz", game)
        original = snapshot(game)
        report = json.loads(run("scan", game))
        assert report["engine"] == "MZ" and report["counts"]["Extracted"] > 0
        assert snapshot(game) == original
        project, bundle, backup = base / "project", base / "bundle", base / "backup"
        run("new", game, project)
        segment = next(s for s in report["segments"] if "Welcome" in s["text"])
        run("edit", project, segment["id"], segment["text"].replace("Welcome", "Hoş geldin 🌙"), "--reviewed", "--lock")
        run("stage", project, bundle)
        assert json.loads(run("apply", game, bundle, backup, "--approve"))["state"] == "Applied"
        assert snapshot(game) != original
        run("restore", game, backup, "--approve")
        assert snapshot(game) == original
    print("PASS: frozen GUI startup and frozen CLI scan/create/edit/stage/apply/restore")


if __name__ == "__main__":
    main()
