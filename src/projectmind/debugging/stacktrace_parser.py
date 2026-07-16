import re


def parse(stacktrace: str) -> list[dict[str, object]]:
    return [
        {"file": m.group(1), "line": int(m.group(2)), "text": m.group(0)}
        for m in re.finditer(r"(?:File \"|at )([^\": ]+).*?(?::|, line )([0-9]+)", stacktrace)
    ]
