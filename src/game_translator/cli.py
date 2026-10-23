import argparse
import json
from pathlib import Path

from . import __version__
from .adapters import scan


def main(argv=None):
    parser = argparse.ArgumentParser(description="Safe RPG Maker file translation")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    scanner = commands.add_parser("scan", help="Read-only source inventory as JSON")
    scanner.add_argument("game", type=Path)
    commands.add_parser("gui", help="Open desktop application")
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            print(json.dumps(scan(args.game).to_dict(), ensure_ascii=False, indent=2))
        elif args.command == "gui":
            from .desktop import main as desktop_main
            desktop_main()
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
