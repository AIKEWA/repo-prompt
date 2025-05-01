import importlib


def test_assess_implementation_readiness_runs():
    implementation_tools = importlib.import_module("src.implementation_tools")
    report = implementation_tools.assess_implementation_readiness()
    assert report.checks, "Should return at least one check"
    assert isinstance(report.all_ok, bool)