"""Corpus discovery and ``task.toml`` parsing.

Tasks are read-only benchmark items under ``tasks/<task_id>/`` (C-004/FR-001).
Discovery includes only directories that contain ``task.toml``, ``instruction.md``,
and ``tests/test.sh``. Malformed toml fails fast with a ``CorpusError`` naming the
task id and the missing key.
"""

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .config import INSTRUCTION_MD, TASK_TOML, TEST_SH, TESTS_DIRNAME
from .errors import CorpusError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Task:
    """A single read-only benchmark task parsed from ``task.toml``."""

    task_id: str
    language: str
    display_title: str
    base_commit: str
    docker_image: str
    cpus: int
    memory_mb: int
    allow_internet: bool
    agent_timeout_sec: float
    verifier_timeout_sec: float
    build_timeout_sec: float
    task_dir: Path
    instruction_path: Path
    tests_dir: Path


def _require(table: dict, section: str, key: str, task_id: str):
    """Return ``table[key]`` or raise ``CorpusError`` naming the missing key."""
    if key not in table:
        raise CorpusError(
            f"Task '{task_id}': missing required key [{section}].{key} in {TASK_TOML}."
        )
    return table[key]


def parse_task(task_dir: Path) -> Task:
    """Parse a task directory's ``task.toml`` into a ``Task``.

    Raises:
        CorpusError: when the toml is unreadable or a required key is absent.
    """
    toml_path = task_dir / TASK_TOML
    task_id = task_dir.name
    try:
        with toml_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise CorpusError(f"Task '{task_id}': cannot read {TASK_TOML}: {exc}") from exc

    metadata = _require(data, "", "metadata", task_id)
    environment = _require(data, "", "environment", task_id)
    agent = _require(data, "", "agent", task_id)
    verifier = _require(data, "", "verifier", task_id)

    return Task(
        task_id=_require(metadata, "metadata", "task_id", task_id),
        language=_require(metadata, "metadata", "language", task_id),
        display_title=_require(metadata, "metadata", "display_title", task_id),
        base_commit=_require(metadata, "metadata", "base_commit_hash", task_id),
        docker_image=_require(environment, "environment", "docker_image", task_id),
        cpus=int(_require(environment, "environment", "cpus", task_id)),
        memory_mb=int(_require(environment, "environment", "memory_mb", task_id)),
        allow_internet=bool(_require(environment, "environment", "allow_internet", task_id)),
        agent_timeout_sec=float(_require(agent, "agent", "timeout_sec", task_id)),
        verifier_timeout_sec=float(_require(verifier, "verifier", "timeout_sec", task_id)),
        build_timeout_sec=float(_require(environment, "environment", "build_timeout_sec", task_id)),
        task_dir=task_dir,
        instruction_path=task_dir / INSTRUCTION_MD,
        tests_dir=task_dir / TESTS_DIRNAME,
    )


def _is_task_dir(candidate: Path) -> bool:
    """Return True if ``candidate`` has the three required corpus task files."""
    return (
        (candidate / TASK_TOML).is_file()
        and (candidate / INSTRUCTION_MD).is_file()
        and (candidate / TESTS_DIRNAME / TEST_SH).is_file()
    )


def discover_tasks(corpus_root: Path) -> dict[str, Task]:
    """Discover and parse every valid task under ``corpus_root``.

    Directories lacking ``task.toml`` + ``instruction.md`` + ``tests/test.sh`` are
    skipped with a debug log (they are not valid corpus tasks). Returns a mapping
    of ``task_id`` to ``Task``.

    Raises:
        CorpusError: when ``corpus_root`` does not exist.
    """
    if not corpus_root.is_dir():
        raise CorpusError(f"Corpus root does not exist or is not a directory: {corpus_root}")

    tasks: dict[str, Task] = {}
    for candidate in sorted(corpus_root.iterdir()):
        if not candidate.is_dir():
            continue
        if not _is_task_dir(candidate):
            logger.debug("Skipping non-task directory: %s", candidate.name)
            continue
        task = parse_task(candidate)
        tasks[task.task_id] = task

    logger.info("Discovered %d tasks under %s", len(tasks), corpus_root)
    return tasks
