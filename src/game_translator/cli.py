import argparse
import json
import sqlite3
import sys
from pathlib import Path

from . import __version__
from .adapters import scan
from .storage import Project
from .jobs import create_job, job_report, run_job
from .providers import DeepLProvider, ProviderError
from .patching import apply, restore, stage


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Safe RPG Maker file translation")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    scanner = commands.add_parser("scan", help="Read-only source inventory as JSON")
    scanner.add_argument("game", type=Path)
    creator = commands.add_parser("new", help="Scan and create a separate SQLite project")
    creator.add_argument("game", type=Path)
    creator.add_argument("project", type=Path)
    creator.add_argument("--source", default="EN")
    creator.add_argument("--target", default="TR")
    status = commands.add_parser("status", help="Project progress and segment IDs")
    status.add_argument("project", type=Path)
    editor = commands.add_parser("edit", help="Save a validated manual translation")
    editor.add_argument("project", type=Path)
    editor.add_argument("segment_id")
    editor.add_argument("text")
    editor.add_argument("--reviewed", action="store_true")
    editor.add_argument("--lock", action="store_true")
    glossary = commands.add_parser("glossary", help="Add an approved target-language term")
    glossary.add_argument("project", type=Path)
    glossary.add_argument("term")
    glossary.add_argument("translation")
    translator = commands.add_parser("translate", help="Create/resume a DeepL batch job")
    translator.add_argument("project", type=Path)
    translator.add_argument("--job", help="Resume an existing job ID")
    translator.add_argument("--allow-cloud", action="store_true", help="Consent to sending text to DeepL; charges may apply")
    translator.add_argument("--batch-size", type=int, default=20)
    jobs = commands.add_parser("jobs", help="Show job checkpoints and errors")
    jobs.add_argument("project", type=Path)
    staging = commands.add_parser("stage", help="Stage reviewed translations outside the game")
    staging.add_argument("project", type=Path)
    staging.add_argument("output", type=Path)
    applying = commands.add_parser("apply", help="Validate, back up and apply a staged patch")
    applying.add_argument("game", type=Path)
    applying.add_argument("bundle", type=Path)
    applying.add_argument("backup", type=Path)
    applying.add_argument("--approve", action="store_true")
    restoring = commands.add_parser("restore", help="Restore exact original bytes from a verified backup")
    restoring.add_argument("game", type=Path)
    restoring.add_argument("backup", type=Path)
    restoring.add_argument("--approve", action="store_true")
    for command in (status, editor, glossary, translator, jobs, staging):
        command.add_argument("--target", help="Operate on another target language without changing the default")
    commands.add_parser("gui", help="Open desktop application")
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            print(json.dumps(scan(args.game).to_dict(), ensure_ascii=False, indent=2))
        elif args.command == "gui":
            from .desktop import main as desktop_main
            desktop_main()
        elif args.command == "new":
            project = Project.create(args.project, scan(args.game), args.source, args.target)
            print(json.dumps(project.progress()))
            project.close()
        elif args.command == "stage":
            project = Project(args.project)
            try:
                if args.target:
                    project.set_target(args.target, persist=False)
                print(json.dumps(stage(project, args.output), ensure_ascii=False, indent=2))
            finally:
                project.close()
        elif args.command == "apply":
            print(json.dumps(apply(args.game, args.bundle, args.backup, args.approve)))
        elif args.command == "restore":
            print(json.dumps(restore(args.game, args.backup, args.approve)))
        elif args.command in ("status", "edit", "glossary", "translate", "jobs"):
            project = Project(args.project)
            try:
                if args.target:
                    project.set_target(args.target, persist=False)
                if args.command == "edit":
                    project.save_translation(args.segment_id, args.text, reviewed=args.reviewed, locked=args.lock)
                elif args.command == "glossary":
                    project.set_glossary(args.term, args.translation)
                    print(json.dumps(project.glossary(), ensure_ascii=False))
                    return
                elif args.command == "translate":
                    if not args.allow_cloud:
                        raise ValueError("Use --allow-cloud to consent to DeepL data transfer and possible charges")
                    provider = DeepLProvider()
                    provider.validate_configuration()
                    job_id = args.job or create_job(project)
                    print(f"Job: {job_id}")
                    try:
                        result = run_job(project, job_id, provider, batch_size=args.batch_size)
                    except KeyboardInterrupt:
                        print("Interrupted; resume with --job " + job_id)
                        return
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    if result["failed"]:
                        parser.exit(2, "Translation job has failures; inspect the job report before retrying.\n")
                    return
                elif args.command == "jobs":
                    print(json.dumps([job_report(project, r[0]) for r in project.db.execute("SELECT id FROM jobs WHERE target=?", (project.target,))], ensure_ascii=False, indent=2))
                    return
                print(json.dumps({"progress": project.progress(), "segments": [
                    {"id": s.id, "source": s.text, "context": s.context,
                     "translation": dict(project.translation(s.id)) if project.translation(s.id) else None}
                    for s in project.segments()]}, ensure_ascii=False, indent=2))
            finally:
                project.close()
    except (ValueError, OSError, ProviderError, sqlite3.Error) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
