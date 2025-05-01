from pathlib import Path

from src.developer_needs import analyze_developer_needs, Need
from src.success_metrics import MetricsStore, EnergyEvent, OverrideEvent, LocalOperationEvent


def _seed_metrics(tmp_path: Path):
    """Write a sample metrics file inside *tmp_path* and return its path."""

    store_path = tmp_path / "metrics.jsonl"
    store = MetricsStore(store_path)

    # Energy footprint – simulate mixed local/remote usage
    store.append_event(EnergyEvent(tokens=1000, energy_kwh=0.2, local_execution=False))
    store.append_event(EnergyEvent(tokens=500, energy_kwh=0.05, local_execution=True))

    # Local operation events (75% local)
    for _ in range(3):
        store.append_event(LocalOperationEvent(local_operation_success=True))
    store.append_event(LocalOperationEvent(local_operation_success=False))

    # Override events (25% overrides)
    for flag in [True, False, False, False]:
        store.append_event(OverrideEvent(override=flag))

    return store_path


def test_analyze_developer_needs(tmp_path):
    metrics_file = _seed_metrics(tmp_path)

    data = analyze_developer_needs(metrics_file)

    # Basic structure checks
    assert "needs" in data
    assert Need.ENVIRONMENTAL_FOOTPRINT in data["needs"]
    assert Need.TRANSPARENCY in data["needs"]
    assert Need.AGENCY in data["needs"]

    # Recommendation list should not be empty given the seeded values
    assert data["recommendations"], "Expected at least one recommendation"