from pathlib import Path

from src.growth_resource_allocation import seed_growth_resources
from src.resource_allocation import ResourceStore


def test_seed_growth_resources(tmp_path: Path) -> None:
    """Seeding should add the expected number of personnel entries."""

    store_file = tmp_path / "ra.jsonl"

    # Ensure the preset can be seeded without exceptions
    seed_growth_resources(store_file)

    # Validate aggregation counts
    store = ResourceStore(store_file)
    summary = store.aggregate()

    expected_roles = {
        "DevOps": 1,
        "Growth PM": 1,
        "Backend Dev": 2,
        "Marketing": 1,
        "Customer Success": 1,
    }

    assert summary["personnel"] == expected_roles