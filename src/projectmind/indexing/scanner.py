from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from ..core.config import Config
from ..core.db import Database
from .framework_detector import detect_framework
from .symbol_extractor import extract_symbols, language_for

_PY_STDLIB = {
    "os",
    "sys",
    "json",
    "re",
    "typing",
    "collections",
    "pathlib",
    "datetime",
    "math",
    "itertools",
    "functools",
    "asyncio",
    "logging",
    "abc",
    "enum",
    "dataclasses",
    "unittest",
    "pytest",
}
_JS_BUILTIN = {"react", "fs", "path", "http", "os", "util"}


def extract_imports(content: str, language: str) -> list[str]:
    modules: list[str] = []
    if language == "python":
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("import "):
                rest = line[len("import "):].strip()
                for part in rest.split(","):
                    top = part.strip().split()[0].split(".")[0]
                    if top and top not in _PY_STDLIB:
                        modules.append(top)
            elif line.startswith("from "):
                rest = line[len("from "):].strip()
                top = rest.split()[0].split(".")[0]
                if top and top != "__future__" and top not in _PY_STDLIB:
                    modules.append(top)
    elif language in ("javascript", "typescript"):
        for m in __import__("re").finditer(
            r"import\s+(?:[^'\"\n]+?\s+from\s+)?['\"]([^'\"]+)['\"]|require\(\s*['\"]([^'\"]+)['\"]\s*\)",
            content,
        ):
            spec = m.group(1) or m.group(2)
            if not spec:
                continue
            top = spec.lstrip("./").split("/")[0].split(".")[0]
            if top and top not in _JS_BUILTIN:
                modules.append(top)
    seen: set[str] = set()
    unique: list[str] = []
    for mod in modules:
        if mod not in seen:
            seen.add(mod)
            unique.append(mod)
    return unique


def iter_files(config: Config, scope: str | None = None):
    base = config.safe_path(scope or ".")
    if base.is_file():
        yield base
        return
    for path in base.rglob("*"):
        if path.is_file() and not any(part in config.excludes for part in path.parts):
            if path.suffix.lower() in {
                ".py",
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                ".java",
                ".go",
                ".rs",
                ".rb",
                ".php",
                ".cs",
                ".sql",
                ".md",
                ".toml",
                ".json",
                ".yaml",
                ".yml",
            }:
                yield path


def scan(
    config: Config,
    db: Database,
    scope: str | None = None,
    incremental: bool = True,
    include_tests: bool = True,
) -> dict[str, object]:
    indexed = 0
    skipped = 0
    for path in iter_files(config, scope):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        digest = hashlib.sha256(content.encode()).hexdigest()
        rel = str(path.relative_to(config.root)).replace("\\", "/")
        old = db.one("SELECT hash,id FROM files WHERE path=?", (rel,))
        if incremental and old and old["hash"] == digest:
            skipped += 1
            continue
        is_test = int(
            path.name.startswith("test_")
            or path.name.endswith(("_test.py", ".test.js", ".spec.ts"))
            or "tests" in path.parts
        )
        cur = db.execute(
            "INSERT INTO files(path,language,framework,hash,size_bytes,last_indexed_at,is_test,content) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET language=excluded.language,framework=excluded.framework,hash=excluded.hash,size_bytes=excluded.size_bytes,last_indexed_at=excluded.last_indexed_at,is_test=excluded.is_test,content=excluded.content",
            (
                rel,
                language_for(path),
                detect_framework(config.root, content),
                digest,
                len(content.encode()),
                datetime.now(UTC).isoformat(),
                is_test,
                content,
            ),
        )
        file_id = old["id"] if old else cur.lastrowid
        db.execute("DELETE FROM symbols WHERE file_id=?", (file_id,))
        for symbol in extract_symbols(path, content):
            db.execute(
                "INSERT INTO symbols(file_id,name,qualified_name,kind,start_line,end_line,signature,docstring,complexity) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    file_id,
                    symbol["name"],
                    symbol["qualified_name"],
                    symbol["kind"],
                    symbol["start_line"],
                    symbol["end_line"],
                    symbol["signature"],
                    symbol["docstring"],
                    symbol["complexity"],
                ),
            )
        db.execute("DELETE FROM files_fts WHERE rowid=?", (file_id,))
        db.execute(
            "INSERT INTO files_fts(rowid,path,content) VALUES(?,?,?)", (file_id, rel, content)
        )
        db.execute(
            "DELETE FROM symbols_fts WHERE rowid IN (SELECT id FROM symbols WHERE file_id=?)",
            (file_id,),
        )
        for symbol in db.rows(
            "SELECT id,name,qualified_name,signature,docstring FROM symbols WHERE file_id=?",
            (file_id,),
        ):
            db.execute(
                "INSERT INTO symbols_fts(rowid,name,qualified_name,signature,docstring) VALUES(?,?,?,?,?)",
                (
                    symbol["id"],
                    symbol["name"],
                    symbol["qualified_name"],
                    symbol["signature"] or "",
                    symbol["docstring"] or "",
                ),
            )
        db.execute(
            "DELETE FROM edges WHERE source_type='file' AND source_id=?", (file_id,)
        )
        for mod in extract_imports(content, language_for(path)):
            target_id = _resolve_import_file(db, config, mod)
            if target_id is not None and target_id != file_id:
                db.execute(
                    "INSERT INTO edges(source_type,source_id,target_type,target_id,relation,confidence) VALUES('file',?, 'file',?, 'IMPORTS', 1.0)",
                    (file_id, target_id),
                )
        indexed += 1
    return {"indexed": indexed, "skipped": skipped, "total": indexed + skipped}


def _resolve_import_file(db: "Database", config: Config, mod: str) -> int | None:
    candidates = [
        f"{mod.replace('.', '/')}.py",
        f"{mod.replace('.', '/')}/__init__.py",
    ]
    for cand in candidates:
        row = db.one("SELECT id FROM files WHERE path=?", (cand,))
        if row:
            return row["id"]
    return None
