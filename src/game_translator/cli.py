import argparse
import json
from pathlib import Path

from . import __version__
from .adapters import scan
from .storage import Project


def main(argv=None):
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
        elif args.command in ("status", "edit"):
            project = Project(args.project)
            try:
                if args.command == "edit":
                    project.save_translation(args.segment_id, args.text, reviewed=args.reviewed, locked=args.lock)
                print(json.dumps({"progress": project.progress(), "segments": [
                    {"id": s.id, "source": s.text, "context": s.context,
                     "translation": dict(project.translation(s.id)) if project.translation(s.id) else None}
                    for s in project.segments()]}, ensure_ascii=False, indent=2))
            finally:
                project.close()
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
