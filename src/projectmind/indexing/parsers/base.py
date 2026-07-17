"""Language-neutral parser records used by the indexing extractor."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ParsedSymbol:
    kind: str
    name: str
    qualname: str
    start_line: int
    end_line: int
    container: str | None = None
    complexity: float | None = None
    loc: int | None = None
    method_count: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedImport:
    module: str
    line: int
    names: tuple[str, ...] = ()
    relative_level: int = 0


@dataclass(frozen=True, slots=True)
class ParsedRelation:
    relation: str
    source_qualname: str | None
    target_ref: str
    line: int
    confidence: float = 1.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedRoute:
    method: str
    route_path: str
    handler_qualname: str | None
    line: int
    framework: str


@dataclass(frozen=True, slots=True)
class ParsedTable:
    name: str
    owner_qualname: str | None
    line: int
    orm: str
    access: str = "read_write"


@dataclass(frozen=True, slots=True)
class ParseResult:
    symbols: tuple[ParsedSymbol, ...] = ()
    imports: tuple[ParsedImport, ...] = ()
    relations: tuple[ParsedRelation, ...] = ()
    routes: tuple[ParsedRoute, ...] = ()
    tables: tuple[ParsedTable, ...] = ()
    errors: tuple[str, ...] = ()
    adapter: str = "unknown"
    confidence: float = 1.0


class LanguageParser(Protocol):
    language: str

    def parse(self, source: str, path: Path) -> ParseResult: ...


ParserAdapter = LanguageParser


__all__ = [
    "LanguageParser",
    "ParseResult",
    "ParsedImport",
    "ParsedRelation",
    "ParsedRoute",
    "ParsedSymbol",
    "ParsedTable",
    "ParserAdapter",
]
