"""Compatibility names for the standard-library Python parser."""

from projectmind.indexing.parsers.python_ast import PythonASTParser

PythonParser = PythonASTParser

__all__ = ["PythonASTParser", "PythonParser"]
