"""Per-task container lifecycle and the online agent phase (FR-006/007/011/013/014).

Starts ONE container per task (network ON) with the runtime mounted read-only, a
writable Claude config at the container HOME ``.claude``, a host log dir at ``/logs``,
and a ``/work`` dir for the prompt. The held-out ``tests/`` directory is deliberately
NOT mounted here, so the hidden tests physically do not exist during the agent phase
(hard isolation, FR-005/FR-018); they are injected by the grader at grading time.
The prompt is fed to ``claude -p`` on stdin (not shell-interpolated) so multi-KB
instructions with backticks/quotes/newlines are not mangled; the slash token stays the
first line so Claude Code expands it.
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config
from .corpus import Task
from .docker_cli import DockerCli, DockerResult
from .errors import AgentError
from .preflight import Credential
from .prompt import WorkflowRef, build_prompt

logger = logging.getLogger(__name__)


@dataclass
class AgentOutcome:
    """The result of the agent phase for one task."""

    container_id: str
    exit_code: Optional[int]
    duration_sec: float
    timed_out: bool
    stdout: str
    stderr: str


def _build_run_args(
    task: Task, credential: Credential, runtime_dir: Path, config_dir: Path
) -> list[str]:
    """Build the ``docker run -d`` argv: limits, network on, credential env, mounts.

    The credential is forwarded by NAME only (``-e ANTHROPIC_API_KEY``) so its value is
    inherited from the child env and never appears in argv (security, T045).
    """
    home_claude = f"{config.CONTAINER_HOME}/.claude"
    return [
        "-d",
        "--cpus", str(task.cpus),
        "--memory", f"{task.memory_mb}m",
        "-e", credential.env_var,
        "-v", f"{runtime_dir}:{config.MOUNT_RUNTIME}:ro",
        "-v", f"{config_dir}:{home_claude}",
        "-w", config.CONTAINER_APP_DIR,
        task.docker_image,
        "sleep", "infinity",
    ]


def _start_container(
    task: Task, credential: Credential, runtime_dir: Path, config_dir: Path, docker: DockerCli
) -> str:
    """Start the detached container and return its id.

    Raises:
        AgentError: when the container fails to start (caller maps to NOT_ATTEMPTED).
    """
    result = docker.run_detached(_build_run_args(task, credential, runtime_dir, config_dir))
    if not result.ok:
        raise AgentError(
            f"Task '{task.task_id}': container failed to start "
            f"(docker exit {result.returncode}): {result.stderr.strip()[-300:]}"
        )
    container_id = result.stdout.strip()
    if not container_id:
        raise AgentError(f"Task '{task.task_id}': docker run returned no container id.")
    logger.info("Task '%s': started container %s", task.task_id, container_id[:12])
    return container_id


def _prepare_logs(container_id: str, docker: DockerCli) -> None:
    """Pre-create ``/logs/verifier`` and ``/logs/artifacts`` inside the container (R8)."""
    verifier_dir = f"{config.MOUNT_LOGS}/{config.LOGS_VERIFIER_SUBDIR}"
    artifacts_dir = f"{config.MOUNT_LOGS}/{config.LOGS_ARTIFACTS_SUBDIR}"
    work_dir = config.MOUNT_WORK
    docker.exec(container_id, ["mkdir", "-p", verifier_dir, artifacts_dir, work_dir])


def _build_agent_command(model: str) -> list[str]:
    """Build the ``env ... claude -p`` argv executed inside the container.

    Sets HOME (so claude finds the mounted ``.claude``), a PATH with the runtime bins
    first, and ``IS_SANDBOX=1`` - claude refuses ``bypassPermissions`` as root (the task
    containers run as root) unless this is set. ``IS_SANDBOX`` is not a secret, so it is
    inlined here; the credential is forwarded separately by name (never in argv).
    """
    runtime = config.MOUNT_RUNTIME
    return [
        "env",
        f"HOME={config.CONTAINER_HOME}",
        f"{config.ENV_IS_SANDBOX}={config.IS_SANDBOX_VALUE}",
        f"PATH={runtime}/npm/bin:{runtime}:/usr/local/sbin:/usr/local/bin:"
        "/usr/sbin:/usr/bin:/sbin:/bin",
        "claude", "-p",
        "--permission-mode", "bypassPermissions",
        "--output-format", "json",
        "--model", model,
        "--append-system-prompt", config.BENCHMARK_DIRECTIVE,
    ]


def _exec_agent(
    container_id: str, task: Task, credential: Credential, prompt_text: str, model: str,
    docker: DockerCli,
) -> tuple[DockerResult, bool]:
    """Exec ``claude -p`` headlessly with the prompt on stdin; honor the agent timeout.

    Returns the docker result and whether the host-side timeout fired.
    """
    command = _build_agent_command(model)
    try:
        result = docker.exec(
            container_id, command, timeout=task.agent_timeout_sec,
            env=[credential.env_var], workdir=config.CONTAINER_APP_DIR, stdin_text=prompt_text,
        )
        return result, False
    except subprocess.TimeoutExpired:
        logger.warning(
            "Task '%s': agent phase timed out after %.0fs",
            task.task_id, task.agent_timeout_sec,
        )
        return DockerResult(args=command, returncode=124, stdout="", stderr="timeout"), True


def run_agent(
    task: Task, ref: WorkflowRef, credential: Credential, model: str,
    runtime_dir: Path, config_dir: Path, docker: DockerCli,
) -> AgentOutcome:
    """Run the full online agent phase for one task and return its outcome.

    The container is started and left RUNNING for the subsequent grading phase
    (the caller force-removes it). ``duration_sec`` is the agent exec wall-clock.

    Raises:
        AgentError: when the container cannot be started (provisioning failure).
    """
    instruction_text = task.instruction_path.read_text(encoding="utf-8")
    prompt_text = build_prompt(ref, instruction_text)

    container_id = _start_container(task, credential, runtime_dir, config_dir, docker)
    _prepare_logs(container_id, docker)

    started = time.monotonic()
    result, timed_out = _exec_agent(container_id, task, credential, prompt_text, model, docker)
    duration = time.monotonic() - started

    exit_code = None if timed_out else result.returncode
    logger.info(
        "Task '%s': agent phase finished in %.1fs (exit=%s, timed_out=%s)",
        task.task_id, duration, exit_code, timed_out,
    )
    return AgentOutcome(
        container_id=container_id,
        exit_code=exit_code,
        duration_sec=duration,
        timed_out=timed_out,
        stdout=result.stdout,
        stderr=result.stderr,
    )
