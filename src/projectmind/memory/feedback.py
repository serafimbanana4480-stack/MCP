from .store import MemoryStore


def record_feedback(store: MemoryStore, context_ref: str, signal: str, note: str = "") -> dict:
    return store.feedback(context_ref, signal, note)
