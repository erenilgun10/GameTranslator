import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .adapters import read_json
from .models import ScanReport, Segment
from .tokens import validate_translation


def now():
    return datetime.now(timezone.utc).isoformat()


def language(value):
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?", value):
        raise ValueError("Invalid language code")
    return value.upper()


class Project:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.manifest = read_json(self.directory / "project.json")
        if self.manifest.get("format") != 1:
            raise ValueError("Unsupported project format")
        self.target = language(self.manifest["target_language"])
        self.source = language(self.manifest["source_language"])
        database = self.directory / "project.sqlite3"
        if database.is_symlink() or not database.is_file():
            raise ValueError("Missing or unsafe project database")
        self.db = sqlite3.connect(database.as_uri() + "?mode=rw", uri=True)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")

    @classmethod
    def create(cls, directory: Path, report: ScanReport, source="EN", target="TR"):
        source, target = language(source), language(target)
        directory = directory.resolve()
        game = Path(report.game).resolve()
        if directory.is_relative_to(game) or game.is_relative_to(directory):
            raise ValueError("Project must be separate from the game")
        if not report.segments:
            raise ValueError("No translatable segments found")
        directory.mkdir(parents=True, exist_ok=False)
        manifest = {"format": 1, "id": str(uuid.uuid4()), "game": report.game,
                    "engine": report.engine, "source_language": source,
                    "target_language": target, "created": now()}
        db = sqlite3.connect(directory / "project.sqlite3")
        try:
            db.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE sources(path TEXT PRIMARY KEY, sha256 TEXT NOT NULL);
                CREATE TABLE segments(id TEXT PRIMARY KEY, file TEXT NOT NULL, path TEXT NOT NULL,
                    text TEXT NOT NULL, context TEXT NOT NULL);
                CREATE TABLE translations(segment_id TEXT NOT NULL REFERENCES segments(id), target TEXT NOT NULL,
                    text TEXT NOT NULL, provider TEXT NOT NULL, status TEXT NOT NULL,
                    locked INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL,
                    PRIMARY KEY(segment_id,target));
                CREATE TABLE history(id INTEGER PRIMARY KEY, segment_id TEXT NOT NULL, target TEXT NOT NULL,
                    text TEXT NOT NULL, provider TEXT NOT NULL, status TEXT NOT NULL, updated TEXT NOT NULL);
            """)
            with db:
                db.executemany("INSERT INTO sources VALUES (?,?)", [(s.path, s.sha256) for s in report.sources])
                db.executemany("INSERT INTO segments VALUES (?,?,?,?,?)", [
                    (s.id, s.file, json.dumps(s.path), s.text, s.context) for s in report.segments])
        finally:
            db.close()
        (directory / "project.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (directory / "scan-report.json").write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return cls(directory)

    def close(self):
        self.db.close()

    def segments(self):
        return [Segment(r["id"], r["file"], tuple(json.loads(r["path"])), r["text"], r["context"])
                for r in self.db.execute("SELECT * FROM segments ORDER BY rowid")]

    def translation(self, segment_id):
        return self.db.execute("SELECT * FROM translations WHERE segment_id=? AND target=?", (segment_id, self.target)).fetchone()

    def save_translation(self, segment_id, text, provider="manual", reviewed=False, locked=False, automatic=False):
        row = self.db.execute("SELECT text FROM segments WHERE id=?", (segment_id,)).fetchone()
        if row is None:
            raise ValueError("Unknown segment")
        validate_translation(row["text"], text)
        existing = self.translation(segment_id)
        if automatic and existing and existing["locked"]:
            raise ValueError("Manual translation is locked")
        status, updated = ("Reviewed" if reviewed else "Translated"), now()
        with self.db:
            if existing:
                self.db.execute("INSERT INTO history(segment_id,target,text,provider,status,updated) VALUES (?,?,?,?,?,?)",
                                (segment_id, self.target, existing["text"], existing["provider"], existing["status"], existing["updated"]))
            self.db.execute("INSERT INTO translations VALUES (?,?,?,?,?,?,?) ON CONFLICT(segment_id,target) DO UPDATE SET text=excluded.text, provider=excluded.provider, status=excluded.status, locked=excluded.locked, updated=excluded.updated",
                            (segment_id, self.target, text, provider, status, int(locked), updated))

    def progress(self):
        total = self.db.execute("SELECT count(*) FROM segments").fetchone()[0]
        rows = dict(self.db.execute("SELECT status,count(*) FROM translations WHERE target=? GROUP BY status", (self.target,)).fetchall())
        translated = sum(rows.values())
        return {"Extracted": total, "Translated": translated, "Reviewed": rows.get("Reviewed", 0),
                "Pending": total - translated, "percent_of_extracted": round(translated * 100 / total, 1) if total else 0}
