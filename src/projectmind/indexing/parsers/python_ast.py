"""Precise Python adapter built on the standard-library AST."""

from __future__ import annotations

import ast
from pathlib import Path

from .base import (
    ParsedImport,
    ParsedRelation,
    ParsedRoute,
    ParsedSymbol,
    ParsedTable,
    ParseResult,
)


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _complexity(node: ast.AST) -> float:
    branching = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.IfExp,
        ast.comprehension,
        ast.Match,
    )
    score = 1
    for child in ast.walk(node):
        if isinstance(child, branching):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(1, len(child.values) - 1)
    return float(score)


class PythonASTParser:
    language = "python"

    def parse(self, source: str, path: Path) -> ParseResult:
        try:
            tree = ast.parse(source, filename=str(path), type_comments=True)
        except (SyntaxError, ValueError) as exc:
            line = getattr(exc, "lineno", None)
            location = f" at line {line}" if line else ""
            return ParseResult(
                errors=(f"Python parse error{location}: {exc}",),
                adapter="python_ast",
                confidence=1.0,
            )
        visitor = _PythonVisitor()
        visitor.visit(tree)
        return ParseResult(
            symbols=tuple(visitor.symbols),
            imports=tuple(visitor.imports),
            relations=tuple(visitor.relations),
            routes=tuple(visitor.routes),
            tables=tuple(visitor.tables),
            adapter="python_ast",
            confidence=1.0,
        )


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.symbols: list[ParsedSymbol] = []
        self.imports: list[ParsedImport] = []
        self.relations: list[ParsedRelation] = []
        self.routes: list[ParsedRoute] = []
        self.tables: list[ParsedTable] = []
        self._scope: list[str] = []
        self._symbol_scope: list[str] = []

    @property
    def current_symbol(self) -> str | None:
        return self._symbol_scope[-1] if self._symbol_scope else None

    def _qualname(self, name: str) -> str:
        return ".".join((*self._scope, name))

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                ParsedImport(alias.name, node.lineno, (alias.asname or alias.name,))
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        names = tuple(alias.name for alias in node.names)
        self.imports.append(ParsedImport(module, node.lineno, names, node.level))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualname = self._qualname(node.name)
        method_count = sum(
            isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) for child in node.body
        )
        self.symbols.append(
            ParsedSymbol(
                kind="class",
                name=node.name,
                qualname=qualname,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                container=self.current_symbol,
                complexity=_complexity(node),
                loc=(node.end_lineno or node.lineno) - node.lineno + 1,
                method_count=method_count,
                metadata={
                    "bases": tuple(filter(None, (_dotted_name(base) for base in node.bases)))
                },
            )
        )
        for base in node.bases:
            target = _dotted_name(base)
            if target:
                self.relations.append(ParsedRelation("inherits", qualname, target, node.lineno))
        table = self._class_table(node)
        if table:
            self.tables.append(ParsedTable(table, qualname, node.lineno, "sqlalchemy"))
        self._scope.append(node.name)
        self._symbol_scope.append(qualname)
        self.generic_visit(node)
        self._symbol_scope.pop()
        self._scope.pop()

    @staticmethod
    def _class_table(node: ast.ClassDef) -> str | None:
        for statement in node.body:
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            targets = (
                statement.targets if isinstance(statement, ast.Assign) else (statement.target,)
            )
            if not any(
                isinstance(target, ast.Name) and target.id == "__tablename__" for target in targets
            ):
                continue
            value = statement.value
            if value is not None:
                return _literal_string(value)
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualname = self._qualname(node.name)
        in_class = bool(self._scope) and any(
            item.kind == "class" and item.qualname == self.current_symbol for item in self.symbols
        )
        is_test = node.name.startswith("test_") or any(
            (_dotted_name(decorator) or "").split(".")[-1] in {"test", "pytest.mark.parametrize"}
            for decorator in node.decorator_list
        )
        kind = "test" if is_test else ("method" if in_class else "function")
        self.symbols.append(
            ParsedSymbol(
                kind=kind,
                name=node.name,
                qualname=qualname,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                container=self.current_symbol,
                complexity=_complexity(node),
                loc=(node.end_lineno or node.lineno) - node.lineno + 1,
                metadata={"async": isinstance(node, ast.AsyncFunctionDef)},
            )
        )
        if is_test and node.name.startswith("test_") and len(node.name) > 5:
            self.relations.append(
                ParsedRelation("tests", qualname, node.name[5:], node.lineno, confidence=0.55)
            )
        self._extract_routes(node, qualname)
        self._scope.append(node.name)
        self._symbol_scope.append(qualname)
        self.generic_visit(node)
        self._symbol_scope.pop()
        self._scope.pop()

    def _extract_routes(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, handler_qualname: str
    ) -> None:
        http_methods = {"get", "post", "put", "patch", "delete", "options", "head", "route"}
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            dotted = _dotted_name(decorator.func) or ""
            method = dotted.rsplit(".", 1)[-1].lower()
            if method not in http_methods or not decorator.args:
                continue
            route_path = _literal_string(decorator.args[0])
            if route_path is None:
                continue
            framework = "fastapi" if dotted.startswith(("app.", "router.")) else "flask"
            if method == "route":
                methods: list[str] = []
                for keyword in decorator.keywords:
                    if keyword.arg == "methods" and isinstance(
                        keyword.value, (ast.List, ast.Tuple)
                    ):
                        methods.extend(
                            value
                            for item in keyword.value.elts
                            if (value := _literal_string(item)) is not None
                        )
                method = "|".join(sorted(value.upper() for value in methods)) or "ANY"
            else:
                method = method.upper()
            self.routes.append(
                ParsedRoute(method, route_path, handler_qualname, decorator.lineno, framework)
            )

    def visit_Call(self, node: ast.Call) -> None:
        target = _dotted_name(node.func)
        if target and self.current_symbol:
            self.relations.append(
                ParsedRelation("calls", self.current_symbol, target, node.lineno, confidence=0.8)
            )
        # SQLAlchemy Core: Table("users", metadata, ...)
        if target and target.rsplit(".", 1)[-1] == "Table" and node.args:
            table_name = _literal_string(node.args[0])
            if table_name:
                self.tables.append(
                    ParsedTable(table_name, self.current_symbol, node.lineno, "sqlalchemy_core")
                )
        self.generic_visit(node)


__all__ = ["PythonASTParser"]
