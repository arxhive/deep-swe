"""Unit tests for corpus discovery and task.toml parsing."""

from pathlib import Path

import pytest

from wfbench.corpus import Task, discover_tasks, parse_task
from wfbench.errors import CorpusError


def test_parse_task_populates_all_fields(synthetic_corpus: Path) -> None:
    """parse_task maps every metadata/task/environment/agent/verifier key."""
    task = parse_task(synthetic_corpus / "alpha-task")

    assert isinstance(task, Task)
    assert task.task_id == "alpha-task"
    assert task.language == "python"
    assert task.display_title == "Alpha synthetic task"
    assert task.base_commit == "aaaa1111bbbb2222cccc3333dddd4444eeee5555"
    assert task.docker_image == "public.ecr.aws/example/synthetic:alpha"
    assert task.cpus == 2
    assert task.memory_mb == 8192
    assert task.allow_internet is False
    assert task.agent_timeout_sec == 1200.0
    assert task.verifier_timeout_sec == 600.0
    assert task.build_timeout_sec == 900.0
    assert task.instruction_path == synthetic_corpus / "alpha-task" / "instruction.md"
    assert task.tests_dir == synthetic_corpus / "alpha-task" / "tests"


def test_discover_tasks_includes_only_valid_dirs(synthetic_corpus: Path) -> None:
    """Discovery returns valid tasks and skips dirs without the required files."""
    tasks = discover_tasks(synthetic_corpus)

    assert set(tasks) == {"alpha-task", "beta-task"}
    assert "not-a-task" not in tasks


def test_discover_tasks_missing_root_raises(tmp_path: Path) -> None:
    """A non-existent corpus root raises CorpusError."""
    with pytest.raises(CorpusError):
        discover_tasks(tmp_path / "does-not-exist")


def test_parse_task_malformed_names_missing_key(malformed_task_dir: Path) -> None:
    """A toml missing a required key raises CorpusError naming the task id and key."""
    with pytest.raises(CorpusError) as excinfo:
        parse_task(malformed_task_dir)

    message = str(excinfo.value)
    assert "broken-task" in message
    assert "language" in message
