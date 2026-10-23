import json
import re
from pathlib import Path, PurePosixPath

from .models import Finding, ScanReport, Segment, SourceFile, digest

MAX_SOURCE_BYTES = 32 * 1024 * 1024
DATABASE_FIELDS = {
    "Actors": ("name", "nickname", "profile"),
    "Classes": ("name",), "Items": ("name", "description"),
    "Weapons": ("name", "description"), "Armors": ("name", "description"),
    "Skills": ("name", "description", "message1", "message2"),
    "States": ("name", "message1", "message2", "message3", "message4"),
    "Enemies": ("name",),
}


def safe_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if not relative or "\\" in relative or ":" in relative or path.is_absolute() or any(p in ("..", ".") for p in relative.split("/")):
        raise ValueError("Unsafe relative path")
    target = root / path
    current = root
    if any(p.is_symlink() or p.is_junction() for p in (root, *root.parents)):
        raise ValueError("Symlink/junction roots are unsupported")
    for part in path.parts:
        current /= part
        if current.is_symlink() or current.is_junction():
            raise ValueError("Symlink/junction paths are unsupported")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path escapes root")
    return target


def source_bytes(path: Path):
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("JSON exceeds 32 MiB safety limit")
    with path.open("rb") as handle:
        raw = handle.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("JSON exceeds 32 MiB safety limit")
    return raw


def parse_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON keys")
            result[key] = value
        return result
    text = raw.decode("utf-8-sig")
    text.encode("utf-8", errors="strict")
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))


def read_json(path: Path):
    return parse_json(source_bytes(path))


class MZAdapter:
    engine = "MZ"
    marker = "js/rmmz_core.js"

    def detect(self, root: Path) -> bool:
        return safe_path(root, self.marker).is_file() and safe_path(root, "data/System.json").is_file()

    def discover_sources(self, root: Path):
        data = safe_path(root, "data")
        return sorted(data.glob("*.json"))

    def extract(self, relative: str, data) -> tuple[list[Segment], list[Finding], int]:
        segments, findings = [], []
        accepted = set()

        def add(value, path):
            if not isinstance(value, str) or not value.strip():
                return
            if re.search(r"<[/a-zA-Z][^>]*>|(?:img|audio|movies)/|\.(?:png|ogg|js)$", value):
                findings.append(Finding(relative, "Warning", f"Skipped markup/asset at {path}"))
                return
            value.encode("utf-8", errors="strict")
            identity = json.dumps([relative, path, value], ensure_ascii=False, separators=(",", ":"))
            segments.append(Segment(digest(identity.encode()), relative, tuple(path), value, f"{relative}:{json.dumps(path)}"))
            accepted.add(tuple(path))

        def fields(obj, path, names):
            if not isinstance(obj, dict):
                raise ValueError(f"Expected object at {path}")
            for name in names:
                if name in obj:
                    if not isinstance(obj[name], str):
                        raise ValueError(f"Expected string at {path + [name]}")
                    add(obj[name], path + [name])

        def commands(items, path):
            if not isinstance(items, list):
                raise ValueError("Event commands must be an array")
            for i, command in enumerate(items):
                if not isinstance(command, dict) or type(command.get("code")) is not int or not isinstance(command.get("parameters"), list):
                    raise ValueError("Invalid event command schema")
                code, params = command["code"], command["parameters"]
                base = path + [i, "parameters"]
                if code in (401, 405, 320, 324, 325):
                    index = 0 if code in (401, 405) else 1
                    if len(params) <= index or not isinstance(params[index], str):
                        raise ValueError("Invalid visible command parameter")
                    add(params[index], base + [index])
                elif code == 102:
                    if not params or not isinstance(params[0], list) or not all(isinstance(v, str) for v in params[0]):
                        raise ValueError("Invalid choice array")
                    for j, value in enumerate(params[0]):
                        add(value, base + [0, j])
                elif code == 101 and self.engine == "MZ" and len(params) > 4:
                    add(params[4], base + [4])
                elif code in (355, 655, 356, 357):
                    findings.append(Finding(relative, "Unsupported", f"Script/plugin command {code} at {path + [i]} skipped"))

        name = Path(relative).stem
        if name in DATABASE_FIELDS or name in ("CommonEvents", "Troops"):
            if not isinstance(data, list):
                raise ValueError("Database must be an array")
            for i, obj in enumerate(data):
                if obj is None:
                    continue
                if name in DATABASE_FIELDS:
                    fields(obj, [i], DATABASE_FIELDS[name])
                elif name == "CommonEvents":
                    commands(obj["list"], [i, "list"])
                else:
                    for j, page in enumerate(obj["pages"]):
                        commands(page["list"], [i, "pages", j, "list"])
        elif re.fullmatch(r"Map\d+", name):
            fields(data, [], ("displayName",))
            for i, event in enumerate(data["events"]):
                if event:
                    for j, page in enumerate(event["pages"]):
                        commands(page["list"], ["events", i, "pages", j, "list"])
        elif name == "System":
            fields(data, [], ("gameTitle", "currencyUnit"))
            for key in ("elements", "skillTypes", "weaponTypes", "armorTypes", "equipTypes"):
                if key in data:
                    if not isinstance(data[key], list):
                        raise ValueError("System type names must be an array")
                    for i, value in enumerate(data[key]):
                        add(value, [key, i])
            terms = data.get("terms", {})
            if not isinstance(terms, dict):
                raise ValueError("System terms must be an object")
            for group, values in terms.items():
                if group not in ("basic", "params", "commands", "messages"):
                    findings.append(Finding(relative, "Unsupported", f"Unknown terms group {group} skipped"))
                    continue
                if isinstance(values, list):
                    for i, value in enumerate(values):
                        add(value, ["terms", group, i])
                elif isinstance(values, dict):
                    fields(values, ["terms", group], tuple(values))
        else:
            return [], [Finding(relative, "Unsupported", "Unknown JSON schema; skipped")], 0

        def count_strings(value):
            if isinstance(value, dict):
                return sum(count_strings(v) for v in value.values())
            if isinstance(value, list):
                return sum(count_strings(v) for v in value)
            return int(isinstance(value, str) and bool(value.strip()))
        return segments, findings, count_strings(data) - len(accepted)

    def validate_source(self, relative, data):
        self.extract(relative, data)


class MVAdapter(MZAdapter):
    """MV uses its own marker and four-parameter Show Text command schema."""
    engine = "MV"
    marker = "js/rpg_core.js"


def detect_game(root: Path):
    root = root.absolute()
    detected = []
    for candidate in (root, root / "www"):
        for adapter in (MZAdapter(), MVAdapter()):
            if adapter.detect(candidate):
                detected.append((candidate, adapter))
    if len(detected) > 1:
        raise ValueError("Ambiguous engine/root markers; select an unambiguous game folder")
    if detected:
        return detected[0]
    raise ValueError("Supported RPG Maker MV/MZ game not detected")


def scan(game: Path) -> ScanReport:
    root, adapter = detect_game(game)
    report = ScanReport(str(root), adapter.engine)
    for path in adapter.discover_sources(root):
        relative = path.relative_to(root).as_posix()
        try:
            safe_path(root, relative)
            raw = source_bytes(path)
            data = parse_json(raw)
            segments, findings, skipped = adapter.extract(relative, data)
            report.sources.append(SourceFile(relative, digest(raw)))
            report.segments.extend(segments)
            report.findings.extend(findings)
            report.skipped += skipped
        except (ValueError, KeyError, TypeError, UnicodeError, OSError, RecursionError) as exc:
            report.findings.append(Finding(relative, "Warning", f"Source rejected: {type(exc).__name__}"))
    if (root / "js/plugins.js").exists():
        report.findings.append(Finding("js/plugins.js", "Unsupported", "Plugin JavaScript skipped; no trusted schema"))
    return report
