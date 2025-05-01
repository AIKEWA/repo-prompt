"""Tests for `trust_metrics` (Step 3.6)."""

from src.trust_metrics import evaluate_trust, process_request


def test_evaluate_trust_structure():
    report = evaluate_trust()
    # Expect three metrics (transparency, consent, HITL) but do not assert exact names
    assert len(report.metrics) == 3, "Expected exactly 3 trust metrics"
    assert 0 <= report.total_score <= 100, "Aggregate score between 0 and 100"


def test_process_request_local(monkeypatch):
    # Ensure remote processing is disabled for deterministic behaviour
    monkeypatch.delenv("ENABLE_REMOTE_PROCESSING", raising=False)
    result = process_request("abc")
    assert result == "cba", "Local processing should reverse the string"