def summarize(content: str, max_chars: int = 800) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return " ".join(lines[:20])[:max_chars]
