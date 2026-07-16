from ..core.models import Provenance


def validate(value: str) -> str:
    return Provenance(value).value
