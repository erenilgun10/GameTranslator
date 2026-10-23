from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


@dataclass(frozen=True)
class Segment:
    id: str
    file: str
    path: tuple[str | int, ...]
    text: str
    context: str


@dataclass(frozen=True)
class SourceFile:
    path: str
    sha256: str


@dataclass(frozen=True)
class Finding:
    file: str
    category: str
    reason: str


@dataclass
class ScanReport:
    game: str
    engine: str
    sources: list[SourceFile] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    skipped: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["counts"] = {"Extracted": len(self.segments), "Translated": 0, "Reviewed": 0, "SkippedSafe": self.skipped,
                            "Unsupported": sum(f.category == "Unsupported" for f in self.findings),
                            "Warning": sum(f.category == "Warning" for f in self.findings)}
        return result
