"""Conservative lexical fallbacks for non-Python languages.

These adapters intentionally recognise only unambiguous, common constructs.
They are not a replacement for a full syntax tree; every emitted relationship
is marked below maximum confidence by the extractor.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace
from pathlib import Path

from .base import (
    ParsedImport,
    ParsedRelation,
    ParsedRoute,
    ParsedSymbol,
    ParsedTable,
    ParseResult,
)


def _brace_end(lines: list[str], start_index: int) -> int:
    """Best-effort inclusive end line for a brace-delimited declaration."""

    depth = 0
    opened = False
    for index in range(start_index, len(lines)):
        # Removing quoted strings prevents the usual JSON/format-string braces
        # from distorting the simple balance calculation.
        clean = re.sub(r"(['\"])(?:\\.|(?!\1).)*\1", "", lines[index])
        for char in clean:
            if char == "{":
                depth += 1
                opened = True
            elif char == "}" and opened:
                depth -= 1
                if depth <= 0:
                    return index + 1
    return start_index + 1


def _symbol(
    kind: str,
    name: str,
    line: int,
    end: int,
    *,
    container: str | None = None,
    metadata: dict[str, object] | None = None,
) -> ParsedSymbol:
    qualname = f"{container}.{name}" if container else name
    return ParsedSymbol(
        kind=kind,
        name=name,
        qualname=qualname,
        start_line=line,
        end_line=max(line, end),
        container=container,
        loc=max(1, end - line + 1),
        metadata=metadata or {"lexical": True},
    )


def _with_method_counts(symbols: list[ParsedSymbol]) -> tuple[ParsedSymbol, ...]:
    counts = Counter(
        symbol.container
        for symbol in symbols
        if symbol.container and symbol.kind in {"method", "test"}
    )
    return tuple(
        replace(symbol, method_count=counts[symbol.qualname])
        if symbol.kind == "class" and counts[symbol.qualname]
        else symbol
        for symbol in symbols
    )


class LexicalParser:
    confidence = 0.7

    def __init__(self, language: str) -> None:
        if language not in {"javascript", "typescript", "go", "rust", "java"}:
            raise ValueError(f"unsupported lexical language: {language}")
        self.language = language

    def parse(self, source: str, path: Path) -> ParseResult:
        if self.language in {"javascript", "typescript"}:
            return self._javascript(source)
        if self.language == "go":
            return self._go(source)
        if self.language == "rust":
            return self._rust(source)
        return self._java(source)

    def _javascript(self, source: str) -> ParseResult:
        lines = source.splitlines()
        symbols: list[ParsedSymbol] = []
        imports: list[ParsedImport] = []
        relations: list[ParsedRelation] = []
        routes: list[ParsedRoute] = []
        tables: list[ParsedTable] = []

        import_patterns = (
            re.compile(r"^\s*import(?:[\s\S]*?\sfrom\s*)?['\"]([^'\"]+)['\"]"),
            re.compile(r"\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)"),
            re.compile(r"^\s*export\s+[^;]*\sfrom\s*['\"]([^'\"]+)['\"]"),
        )
        class_ranges: list[tuple[str, int, int]] = []
        pending_route: tuple[str, str, str, int] | None = None
        pending_test = False
        pending_entity: tuple[str | None, int] | None = None

        for index, line in enumerate(lines):
            line_no = index + 1
            stripped = line.strip()
            if stripped.startswith(("//", "/*", "*")):
                continue
            for pattern in import_patterns:
                match = pattern.search(line)
                if match:
                    imports.append(ParsedImport(match.group(1), line_no))
                    break

            entity = re.search(r"@Entity\s*\(\s*(?:['\"]([^'\"]+)['\"])?", line)
            if entity:
                pending_entity = (entity.group(1), line_no)
            class_match = re.search(
                r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"
                r"(?:\s+extends\s+([A-Za-z_$][\w$\.]*))?",
                line,
            )
            if class_match:
                name = class_match.group(1)
                end = _brace_end(lines, index)
                class_ranges.append((name, line_no, end))
                symbols.append(_symbol("class", name, line_no, end))
                if class_match.group(2):
                    relations.append(
                        ParsedRelation(
                            "inherits",
                            name,
                            class_match.group(2),
                            line_no,
                            self.confidence,
                        )
                    )
                if pending_entity:
                    tables.append(
                        ParsedTable(pending_entity[0] or name, name, pending_entity[1], "typeorm")
                    )
                    pending_entity = None

            function_match = re.search(
                r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)",
                line,
            )
            arrow_match = re.search(
                r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)"
                r"\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
                line,
            )
            declaration = function_match or arrow_match
            if declaration:
                name = declaration.group(1)
                end = _brace_end(lines, index)
                is_test = pending_test
                symbols.append(_symbol("test" if is_test else "function", name, line_no, end))
                if pending_route:
                    method, route_path, framework, route_line = pending_route
                    routes.append(ParsedRoute(method, route_path, name, route_line, framework))
                    pending_route = None
                pending_test = False

            test_decorator = re.search(r"@(Test|test)\b", line)
            pending_test = pending_test or bool(test_decorator)
            test_call = re.search(r"\b(?:it|test)\s*\(\s*['\"]([^'\"]+)['\"]", line)
            if test_call:
                name = test_call.group(1)
                qualname = f"test:{name}"
                symbols.append(_symbol("test", qualname, line_no, _brace_end(lines, index)))

            express = re.search(
                r"\b(?:app|router)\.(get|post|put|patch|delete|options|head|all)\s*\(\s*"
                r"['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z_$][\w$\.]*)",
                line,
                re.IGNORECASE,
            )
            if express:
                routes.append(
                    ParsedRoute(
                        "ANY" if express.group(1).lower() == "all" else express.group(1).upper(),
                        express.group(2),
                        express.group(3),
                        line_no,
                        "express",
                    )
                )
            nest = re.search(
                r"@(Get|Post|Put|Patch|Delete|Options|Head)\s*\(\s*['\"]?([^'\")]+)?",
                line,
            )
            if nest:
                method = nest.group(1).upper()
                route_path = nest.group(2) or "/"
                for candidate_index in range(index + 1, min(index + 6, len(lines))):
                    candidate = re.match(
                        r"^\s*(?:(?:public|private|protected|static|async)\s+)*"
                        r"([A-Za-z_$][\w$]*)\s*\(",
                        lines[candidate_index],
                    )
                    if candidate:
                        owner = next(
                            (
                                name
                                for name, start, end in reversed(class_ranges)
                                if start <= candidate_index + 1 <= end
                            ),
                            None,
                        )
                        handler = f"{owner}.{candidate.group(1)}" if owner else candidate.group(1)
                        routes.append(ParsedRoute(method, route_path, handler, line_no, "nestjs"))
                        break

            prisma = re.finditer(
                r"\bprisma\.([A-Za-z_$][\w$]*)\."
                r"(?:find|create|update|delete|upsert)",
                line,
            )
            for match in prisma:
                owner = next(
                    (
                        name
                        for name, start, end in reversed(class_ranges)
                        if start <= line_no <= end
                    ),
                    None,
                )
                tables.append(ParsedTable(match.group(1), owner, line_no, "prisma"))

        # Methods are only recognised inside a known class range and when the
        # line has a conventional method declaration shape.
        for class_name, start, end in class_ranges:
            for line_no in range(start + 1, min(end, len(lines) + 1)):
                line = lines[line_no - 1]
                method_match = re.match(
                    r"^\s*(?:(?:public|private|protected|static|async|readonly)\s+)*"
                    r"([A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*(?::\s*[^={]+)?\s*\{",
                    line,
                )
                if method_match and method_match.group(1) not in {
                    "if",
                    "for",
                    "while",
                    "switch",
                    "catch",
                }:
                    name = method_match.group(1)
                    if not any(item.qualname == f"{class_name}.{name}" for item in symbols):
                        symbols.append(
                            _symbol(
                                "method",
                                name,
                                line_no,
                                _brace_end(lines, line_no - 1),
                                container=class_name,
                            )
                        )

        return ParseResult(
            symbols=_with_method_counts(symbols),
            imports=tuple(imports),
            relations=tuple(relations),
            routes=tuple(routes),
            tables=tuple(tables),
            adapter=f"{self.language}_lexical",
            confidence=self.confidence,
        )

    def _go(self, source: str) -> ParseResult:
        lines = source.splitlines()
        symbols: list[ParsedSymbol] = []
        imports: list[ParsedImport] = []
        routes: list[ParsedRoute] = []
        in_import_block = False
        for index, line in enumerate(lines):
            line_no = index + 1
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if re.match(r"^\s*import\s*\(", line):
                in_import_block = True
                continue
            if in_import_block and stripped == ")":
                in_import_block = False
                continue
            import_match = re.match(r"^\s*import\s+(?:[\w.]+\s+)?['\"]([^'\"]+)['\"]", line)
            block_match = re.match(r"^\s*(?:[\w.]+\s+)?['\"]([^'\"]+)['\"]", line)
            match = block_match if in_import_block else import_match
            if match:
                imports.append(ParsedImport(match.group(1), line_no))
            type_match = re.match(r"^\s*type\s+([A-Za-z_]\w*)\s+(?:struct|interface)\b", line)
            if type_match:
                name = type_match.group(1)
                symbols.append(_symbol("class", name, line_no, _brace_end(lines, index)))
            function = re.match(
                r"^\s*func\s*(?:\(\s*\w+\s+\*?([A-Za-z_]\w*)\s*\)\s*)?([A-Za-z_]\w*)\s*\(",
                line,
            )
            if function:
                receiver, name = function.groups()
                if name.startswith("Test") and not receiver:
                    kind = "test"
                else:
                    kind = "method" if receiver else "function"
                symbols.append(
                    _symbol(kind, name, line_no, _brace_end(lines, index), container=receiver)
                )
            route = re.search(
                r"\b(?:http\.)?HandleFunc\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([A-Za-z_]\w*)",
                line,
            )
            if route:
                routes.append(
                    ParsedRoute(
                        "ANY",
                        route.group(1),
                        route.group(2),
                        line_no,
                        "net/http",
                    )
                )
        return ParseResult(
            symbols=_with_method_counts(symbols),
            imports=tuple(imports),
            routes=tuple(routes),
            adapter="go_lexical",
            confidence=self.confidence,
        )

    def _rust(self, source: str) -> ParseResult:
        lines = source.splitlines()
        symbols: list[ParsedSymbol] = []
        imports: list[ParsedImport] = []
        routes: list[ParsedRoute] = []
        pending_test = False
        for index, line in enumerate(lines):
            line_no = index + 1
            if line.strip().startswith("//"):
                continue
            use = re.match(r"^\s*(?:pub\s+)?use\s+([^;]+);", line)
            if use:
                imports.append(ParsedImport(use.group(1).strip(), line_no))
            module = re.match(r"^\s*(?:pub\s+)?mod\s+([A-Za-z_]\w*)\s*;", line)
            if module:
                imports.append(ParsedImport(module.group(1), line_no))
            data = re.match(r"^\s*(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z_]\w*)", line)
            if data:
                symbols.append(_symbol("class", data.group(1), line_no, _brace_end(lines, index)))
            if re.search(r"#\s*\[\s*test\s*\]", line):
                pending_test = True
            function = re.match(
                r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?"
                r"fn\s+([A-Za-z_]\w*)",
                line,
            )
            if function:
                name = function.group(1)
                symbols.append(
                    _symbol(
                        "test" if pending_test else "function",
                        name,
                        line_no,
                        _brace_end(lines, index),
                    )
                )
                pending_test = False
            route = re.search(
                r"\.route\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*"
                r"(get|post|put|patch|delete)\s*\(\s*([\w:]+)",
                line,
                re.IGNORECASE,
            )
            if route:
                routes.append(
                    ParsedRoute(
                        route.group(2).upper(),
                        route.group(1),
                        route.group(3),
                        line_no,
                        "rust-web",
                    )
                )
        return ParseResult(
            symbols=_with_method_counts(symbols),
            imports=tuple(imports),
            routes=tuple(routes),
            adapter="rust_lexical",
            confidence=self.confidence,
        )

    def _java(self, source: str) -> ParseResult:
        lines = source.splitlines()
        symbols: list[ParsedSymbol] = []
        imports: list[ParsedImport] = []
        relations: list[ParsedRelation] = []
        routes: list[ParsedRoute] = []
        tables: list[ParsedTable] = []
        classes: list[tuple[str, int, int]] = []
        pending_test = False
        pending_route: tuple[str, str, int] | None = None
        pending_entity = False
        pending_table: str | None = None
        for index, line in enumerate(lines):
            line_no = index + 1
            if line.strip().startswith(("//", "*")):
                continue
            imported = re.match(r"^\s*import\s+(?:static\s+)?([^;]+);", line)
            if imported:
                imports.append(ParsedImport(imported.group(1).strip(), line_no))
            pending_test = pending_test or bool(re.search(r"@Test\b", line))
            pending_entity = pending_entity or bool(re.search(r"@Entity\b", line))
            table = re.search(r"@Table\s*\(\s*name\s*=\s*['\"]([^'\"]+)['\"]", line)
            if table:
                pending_table = table.group(1)
            mapping = re.search(
                r"@(Get|Post|Put|Patch|Delete|Request)Mapping\s*\(\s*"
                r"(?:value\s*=\s*)?['\"]([^'\"]*)['\"]",
                line,
            )
            if mapping:
                route_method = "ANY" if mapping.group(1) == "Request" else mapping.group(1).upper()
                pending_route = (route_method, mapping.group(2) or "/", line_no)
            class_match = re.search(
                r"\b(?:class|interface|enum)\s+([A-Za-z_]\w*)(?:\s+extends\s+([A-Za-z_][\w.]*))?",
                line,
            )
            if class_match:
                name = class_match.group(1)
                end = _brace_end(lines, index)
                classes.append((name, line_no, end))
                symbols.append(_symbol("class", name, line_no, end))
                if class_match.group(2):
                    relations.append(
                        ParsedRelation(
                            "inherits",
                            name,
                            class_match.group(2),
                            line_no,
                            self.confidence,
                        )
                    )
                if pending_entity or pending_table:
                    tables.append(ParsedTable(pending_table or name, name, line_no, "jpa"))
                pending_entity = False
                pending_table = None
            method = re.match(
                r"^\s*(?:(?:public|protected|private|static|final|synchronized|abstract)\s+)+"
                r"(?:<[^>]+>\s+)?[\w<>\[\], ?]+\s+([A-Za-z_]\w*)"
                r"\s*\([^;]*\)\s*(?:throws\s+[^\{]+)?\{?",
                line,
            )
            if method and method.group(1) not in {"if", "for", "while", "switch", "catch"}:
                name = method.group(1)
                owner = next(
                    (
                        class_name
                        for class_name, start, end in reversed(classes)
                        if start <= line_no <= end
                    ),
                    None,
                )
                kind = "test" if pending_test else "method"
                qualname = f"{owner}.{name}" if owner else name
                symbols.append(
                    _symbol(
                        kind,
                        name,
                        line_no,
                        _brace_end(lines, index),
                        container=owner,
                    )
                )
                if pending_route:
                    routes.append(
                        ParsedRoute(
                            *pending_route[:2],
                            qualname,
                            pending_route[2],
                            "spring",
                        )
                    )
                    pending_route = None
                pending_test = False
        return ParseResult(
            symbols=_with_method_counts(symbols),
            imports=tuple(imports),
            relations=tuple(relations),
            routes=tuple(routes),
            tables=tuple(tables),
            adapter="java_lexical",
            confidence=self.confidence,
        )


__all__ = ["LexicalParser"]
