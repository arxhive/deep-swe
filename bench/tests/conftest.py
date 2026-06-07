"""Shared pytest fixtures and marker registration for the wfbench test suite."""

from pathlib import Path

import pytest

FIXTURES_TASKS = Path(__file__).parent / "fixtures" / "tasks"
FIXTURES_MALFORMED = Path(__file__).parent / "fixtures" / "tasks_malformed"


def pytest_configure(config: pytest.Config) -> None:
    """Register the ``integration`` marker so docker tests can be selected/deselected."""
    config.addinivalue_line(
        "markers",
        "integration: docker- and credential-dependent tests; auto-skip when unavailable.",
    )


@pytest.fixture
def synthetic_corpus() -> Path:
    """Return the path to the clean synthetic task corpus (two valid tasks)."""
    return FIXTURES_TASKS


@pytest.fixture
def malformed_task_dir() -> Path:
    """Return the path to a task dir whose ``task.toml`` is missing a required key."""
    return FIXTURES_MALFORMED / "broken-task"
