from pathlib import Path


def detect_modules(root: Path) -> list[str]:
    markers = {"pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml"}
    return [
        str(p.parent.relative_to(root) or ".")
        for p in root.rglob("*")
        if p.is_file()
        and p.name in markers
        and not any(x in p.parts for x in {".git", "node_modules", ".venv"})
    ]
