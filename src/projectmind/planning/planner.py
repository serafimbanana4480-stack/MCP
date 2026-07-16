from ..core.models import VerifiedPlan


def create_plan(**kwargs) -> VerifiedPlan:
    return VerifiedPlan(**kwargs)
