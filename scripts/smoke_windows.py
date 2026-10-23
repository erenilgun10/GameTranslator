"""Exercise a frozen Windows package using synthetic data in a temporary folder."""
import argparse
import hashlib
import json
import os
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
    parser.add_argument("--install", action="store_true", help="Exercise the shipped folder installer before testing")
    parser.add_argument("--isolated-environment", action="store_true", help="Launch executables outside the checkout without Python/API/Tcl environment settings")
    args = parser.parse_args()
    package = args.package.resolve()
    environment = dict(os.environ)
    if args.isolated_environment:
        if os.name != "nt":
            parser.error("Isolated Windows acceptance requires Windows")
        for key in list(environment):
            if key.upper().startswith("PYTHON") or key.upper() in {"DEEPL_API_KEY", "TCL_LIBRARY", "TK_LIBRARY"}:
                del environment[key]
        windows = Path(os.environ["SystemRoot"])
        environment["PATH"] = os.pathsep.join((str(windows / "System32"), str(windows)))
    with tempfile.TemporaryDirectory(prefix="game-translator-smoke-") as temporary:
        base = Path(temporary)
        if args.install:
            powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            install_directory = base / "Kurulum İğüşöç"
            command = [str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                       str(package / "Install-GameTranslator.ps1"), "-InstallDir", str(install_directory)]
            subprocess.run(command, check=True, env=environment, cwd=base, timeout=90)
            installed = snapshot(install_directory)
            repeat = subprocess.run(command, env=environment, cwd=base, capture_output=True, timeout=30)
            assert repeat.returncode != 0 and snapshot(install_directory) == installed, "Installer overwrote an existing installation"
            nested = package / "nested-install-must-not-exist"
            nested_command = command[:-1] + [str(nested)]
            refused = subprocess.run(nested_command, env=environment, cwd=base, capture_output=True, timeout=30)
            assert refused.returncode != 0 and not nested.exists(), "Installer accepted a recursive installation target"
            package = install_directory
            print("PASS: installer, Unicode destination, overwrite refusal and recursive target refusal")

        cli = package / "GameTranslator-CLI.exe"
        def run(*arguments):
            result = subprocess.run([str(cli), *map(str, arguments)], capture_output=True, text=True,
                                    encoding="utf-8", timeout=60, env=environment, cwd=base)
            if result.returncode:
                raise RuntimeError(f"Frozen CLI failed: {result.stderr}")
            return result.stdout
        print("Frozen CLI version:", run("--version").strip())
        subprocess.run([str(package / "GameTranslator.exe"), "--smoke-test"], check=True,
                       timeout=30, env=environment, cwd=base)
        for engine in ("MZ", "MV"):
            game = base / ("synthetic-" + engine.lower())
            shutil.copytree(package / ("examples/synthetic-" + engine.lower()), game)
            original = snapshot(game)
            report = json.loads(run("scan", game))
            assert report["engine"] == engine and report["counts"]["Extracted"] > 0
            assert snapshot(game) == original
            project, bundle, backup = base / (engine + "-project"), base / (engine + "-bundle"), base / (engine + "-backup")
            run("new", game, project)
            segment = next(s for s in report["segments"] if s["file"] == "data/CommonEvents.json")
            translated = "Hoş geldin 🌙 " + segment["text"]
            run("edit", project, segment["id"], translated, "--reviewed", "--lock")
            run("edit", project, segment["id"], "SYNTHETISCH " + segment["text"], "--target", "DE", "--reviewed")
            status = json.loads(run("status", project))
            saved = next(s for s in status["segments"] if s["id"] == segment["id"])
            assert saved["translation"]["text"] == translated
            run("stage", project, bundle)
            assert json.loads(run("apply", game, bundle, backup, "--approve"))["state"] == "Applied"
            assert snapshot(game) != original
            patched_text = json.loads((game / segment["file"]).read_text(encoding="utf-8"))
            for part in segment["path"]:
                patched_text = patched_text[part]
            assert patched_text == translated
            assert json.loads(run("apply", game, bundle, backup, "--approve"))["state"] == "AlreadyApplied"
            run("restore", game, backup, "--approve")
            assert snapshot(game) == original
            assert json.loads(run("restore", game, backup, "--approve"))["files"] == 0
            print(f"PASS: {engine} frozen scan/create/Unicode edit/target isolation/stage/apply/idempotence/exact restore")
    print("PASS: frozen GUI startup and MV/MZ CLI acceptance" + (" in isolated environment" if args.isolated_environment else ""))


if __name__ == "__main__":
    main()
