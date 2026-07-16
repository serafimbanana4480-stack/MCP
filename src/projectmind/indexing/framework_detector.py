from pathlib import Path


def detect_framework(root: Path, content: str = "") -> str | None:
    names = {p.name for p in root.iterdir()} if root.exists() else set()
    text = content.lower()
    if "django" in text or "manage.py" in names:
        return "django"
    if "fastapi" in text:
        return "fastapi"
    if "react" in text or "next" in text:
        return "react"
    if "pytest" in text:
        return "pytest"
    return None
