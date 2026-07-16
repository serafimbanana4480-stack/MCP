from pathlib import Path


def update(root: Path, summary: str = "") -> dict:
    readme = root / "README.md"
    return {
        "updated": False,
        "target": str(readme),
        "message": "Documentação viva requer confirmação explícita via propose_edit.",
        "summary": summary,
    }
