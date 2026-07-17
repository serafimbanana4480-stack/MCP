"""Parser registry with no hard dependency on tree-sitter."""

from __future__ import annotations

from pathlib import Path

from projectmind.indexing.discovery import detect_language

from .base import (
    LanguageParser,
    ParsedImport,
    ParsedRelation,
    ParsedRoute,
    ParsedSymbol,
    ParsedTable,
    ParseResult,
)
from .lexical import LexicalParser
from .python_ast import PythonASTParser

# Historical/documentation-facing name for the parser protocol.
ParserAdapter = LanguageParser


class ParserRegistry:
    """Select a deterministic built-in parser by language or extension."""

    def __init__(self) -> None:
        self._parsers: dict[str, LanguageParser] = {
            "python": PythonASTParser(),
            "javascript": LexicalParser("javascript"),
            "typescript": LexicalParser("typescript"),
            "go": LexicalParser("go"),
            "rust": LexicalParser("rust"),
            "java": LexicalParser("java"),
        }

    def register(self, language: str, parser: LanguageParser) -> None:
        self._parsers[language.lower()] = parser

    def for_language(self, language: str) -> LanguageParser:
        try:
            return self._parsers[language.lower()]
        except KeyError as exc:
            raise ValueError(f"unsupported language: {language}") from exc

    def for_path(self, path: Path | str) -> LanguageParser:
        language = detect_language(path)
        if language is None:
            raise ValueError(f"unsupported source extension: {Path(path).suffix}")
        return self.for_language(language)

    def parse(self, source: str, path: Path | str, language: str | None = None) -> ParseResult:
        source_path = Path(path)
        parser = self.for_language(language) if language else self.for_path(source_path)
        return parser.parse(source, source_path)

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._parsers))


__all__ = [
    "LanguageParser",
    "LexicalParser",
    "ParseResult",
    "ParsedImport",
    "ParsedRelation",
    "ParsedRoute",
    "ParsedSymbol",
    "ParsedTable",
    "ParserAdapter",
    "ParserRegistry",
    "PythonASTParser",
]
