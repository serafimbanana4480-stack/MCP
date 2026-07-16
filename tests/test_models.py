from projectmind.core.models import RiskEntry, VerifiedPlan


def test_models_validate_ranges_and_risk_score():
    assert RiskEntry(title="x", probability=0.5, impact=0.8).score == 0.4
    assert VerifiedPlan(objective="ship", assumptions=["local"]).status == "draft"
