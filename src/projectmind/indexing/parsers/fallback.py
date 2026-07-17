"""Compatibility export for conservative lexical adapters."""

from projectmind.indexing.parsers.lexical import LexicalParser

FallbackParser = LexicalParser

__all__ = ["FallbackParser", "LexicalParser"]
