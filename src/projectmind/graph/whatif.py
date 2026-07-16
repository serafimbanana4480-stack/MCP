from .impact import impact
from .store import GraphStore


def simulate(store: GraphStore, target: str, change_type: str, depth: int = 2) -> dict[str, object]:
    result = impact(store, target, depth)
    result.update(
        {
            "change_type": change_type,
            "warning": "Simulação em memória; nenhum ficheiro foi alterado.",
        }
    )
    return result
