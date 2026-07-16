from .summarizer import summarize


def hierarchy(content: str, query: str = "") -> dict:
    return {
        "summary": summarize(content),
        "chunks": content[:4000].split("\n\n")[:5],
        "query": query,
    }
