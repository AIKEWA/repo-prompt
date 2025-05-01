from src.real_world_context import analyze_real_world_context, Domain, Regulation


def test_default_domain_mapping():
    data = analyze_real_world_context(Domain.DEVELOPER_TOOLING)
    assert data["domain"] == Domain.DEVELOPER_TOOLING.value
    # GDPR should be part of default regulations
    assert Regulation.GDPR.value in data["regulations"]
    # Controls list should not be empty
    assert data["controls"], "Controls should be populated"