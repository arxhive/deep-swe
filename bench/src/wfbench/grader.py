"""Offline grading phase: inject held-out tests, run the verifier, extract reward (R7/R8).

Grades the SAME still-running container the agent produced, in this exact order:
(1) disconnect the bridge network so grading is offline (C-008/SC-008);
(2) inject the held-out tests via ``docker cp`` (daemon-side, works with no container
    network) - the FIRST moment the hidden tests exist in the container (FR-005/FR-018);
(3) ensure ``/logs/verifier`` and ``/logs/artifacts`` exist (``test.sh`` only creates the
    latter, so the harness must own ``/logs/verifier`` or the reward write fails, R8);
(4) run ``bash /tests/test.sh`` with the verifier timeout.
Reward ``1`` is a pass; anything else (including missing/garbled) is a non-pass with
``reward=None`` (FR-017). An honest test failure raises nothing; classification happens
in ``results``.
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config
from .corpus import Task
from .docker_cli import DockerCli
from .errors import GradingError

logger = logging.getLogger(__name__)


@dataclass
class GradingOutcome:
    """The result of the grading phase for one task."""

    reward: Optional[float]
    verifier_exit_code: Optional[int]
    duration_sec: float
    verifier_log: str
    patch_present: bool
    crashed: bool


def _go_offline(container_id: str, task: Task, docker: DockerCli) -> None:
    """Disconnect the container's bridge network so grading runs offline (R7)."""
    result = docker.network_disconnect(container_id, config.DEFAULT_BRIDGE_NETWORK)
    if not result.ok:
        # Non-fatal: the network may already be absent; log and continue offline-best-effort.
        logger.warning(
            "Task '%s': network disconnect returned non-zero: %s",
            task.task_id, result.stderr.strip()[-200:],
        )


def _inject_tests(container_id: str, task: Task, docker: DockerCli) -> None:
    """Copy the held-out tests into the running container at ``/tests`` (R8).

    Raises:
        GradingError: when the copy fails (the verifier cannot run without its tests).
    """
    source = f"{task.tests_dir}/."
    dest = f"{container_id}:{config.MOUNT_TESTS}"
    result = docker.cp(source, dest)
    if not result.ok:
        raise GradingError(
            f"Task '{task.task_id}': failed to inject tests into the container: "
            f"{result.stderr.strip()[-300:]}"
        )


def _ensure_log_dirs(container_id: str, docker: DockerCli) -> None:
    """Idempotently ensure ``/logs/verifier`` and ``/logs/artifacts`` exist (R8)."""
    verifier_dir = f"{config.MOUNT_LOGS}/{config.LOGS_VERIFIER_SUBDIR}"
    artifacts_dir = f"{config.MOUNT_LOGS}/{config.LOGS_ARTIFACTS_SUBDIR}"
    docker.exec(container_id, ["mkdir", "-p", verifier_dir, artifacts_dir])


def _read_reward(container_id: str, docker: DockerCli) -> Optional[float]:
    """Read ``/logs/verifier/reward.txt``; return a float, or None if absent/garbled (FR-017)."""
    reward_path = f"{config.MOUNT_LOGS}/{config.LOGS_VERIFIER_SUBDIR}/{config.REWARD_FILENAME}"
    result = docker.exec(container_id, ["cat", reward_path])
    if not result.ok:
        logger.warning("No reward file found at %s", reward_path)
        return None
    raw = result.stdout.strip()
    try:
        return float(raw)
    except ValueError:
        logger.warning("Garbled reward value %r; treating as no reward.", raw)
        return None


def _copy_patch_out(container_id: str, dest_dir: Path, docker: DockerCli) -> bool:
    """Copy ``model.patch`` out of the container to ``dest_dir``; return whether non-empty."""
    artifacts = f"{config.MOUNT_LOGS}/{config.LOGS_ARTIFACTS_SUBDIR}"
    container_patch = f"{container_id}:{artifacts}/{config.MODEL_PATCH_FILENAME}"
    host_patch = dest_dir / config.MODEL_PATCH_FILENAME
    result = docker.cp(container_patch, str(host_patch))
    if not result.ok:
        logger.debug("No model.patch artifact to copy out.")
        return False
    return host_patch.exists() and host_patch.stat().st_size > 0


def grade(container_id: str, task: Task, artifacts_dir: Path, docker: DockerCli) -> GradingOutcome:
    """Run the offline grading phase and return its outcome.

    Args:
        container_id: The running container the agent produced.
        task: The task being graded.
        artifacts_dir: Host dir to copy ``model.patch`` into.
        docker: Docker wrapper.

    Returns:
        A ``GradingOutcome`` with reward, verifier exit code, duration, log, and flags.
        ``crashed`` is True when the verifier could not run to completion (timeout or
        harness-level failure), which the caller classifies as ERRORED.

    Raises:
        GradingError: when the held-out tests cannot be injected.
    """
    _go_offline(container_id, task, docker)
    _inject_tests(container_id, task, docker)
    _ensure_log_dirs(container_id, docker)

    started = time.monotonic()
    crashed = False
    verifier_exit: Optional[int] = None
    log_text = ""
    test_sh = f"{config.MOUNT_TESTS}/{config.TEST_SH}"
    try:
        result = docker.exec(container_id, ["bash", test_sh], timeout=task.verifier_timeout_sec)
        verifier_exit = result.returncode
        log_text = (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired:
        crashed = True
        log_text = f"verifier timed out after {task.verifier_timeout_sec:.0f}s"
        logger.warning("Task '%s': %s", task.task_id, log_text)

    duration = time.monotonic() - started
    reward = None if crashed else _read_reward(container_id, docker)
    patch_present = _copy_patch_out(container_id, artifacts_dir, docker)
    logger.info(
        "Task '%s': grading finished in %.1fs (reward=%s, exit=%s, patch=%s)",
        task.task_id, duration, reward, verifier_exit, patch_present,
    )
    return GradingOutcome(
        reward=reward,
        verifier_exit_code=verifier_exit,
        duration_sec=duration,
        verifier_log=log_text,
        patch_present=patch_present,
        crashed=crashed,
    )
