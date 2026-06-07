"""Orchestration: per-task pipeline and the continue-on-failure batch (FR-015/026).

``run_task`` wires the agent phase -> grading phase -> outcome classification, writes
the per-task artifacts and ``result.json``, and ALWAYS force-removes the container in a
``finally`` block (resource cleanup, NFR-003). ``run_workflow`` iterates the selection
sequentially; one task's failure never aborts the batch (NFR-005).
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import agent_runner, config, grader, report
from .agent_runner import AgentOutcome
from .corpus import Task
from .docker_cli import DockerCli
from .errors import AgentError, GradingError
from .preflight import Credential
from .prompt import WorkflowRef
from .results import Comparison, Outcome, Result, Run, build_comparison, build_run, classify_outcome
from .selection import Selection
from .usage import parse_agent_usage
from .write_artifacts import write_json_file, write_text_file

logger = logging.getLogger(__name__)


@dataclass
class RunConfig:
    """Immutable configuration for one invocation (data-model RunConfig)."""

    workflows: list[WorkflowRef]
    selection: Selection
    model: str
    credential: Credential
    corpus_root: Path
    jobs_root: Path
    runtime_cache: Path
    run_id: str
    run_dir: Path


def _task_artifacts_dir(run_dir: Path, task_id: str, slug: str) -> Path:
    """Return the per-task artifacts directory under the run dir, creating it."""
    artifacts = run_dir / "tasks" / task_id / slug
    artifacts.mkdir(parents=True, exist_ok=True)
    return artifacts


def _write_agent_artifacts(artifacts_dir: Path, agent: AgentOutcome) -> None:
    """Persist the agent stdout (``agent.json``) and stderr (``agent.err``)."""
    write_text_file(artifacts_dir / config.AGENT_JSON, agent.stdout)
    write_text_file(artifacts_dir / config.AGENT_ERR, agent.stderr)


def _terminal_result(
    task: Task, ref: WorkflowRef, cfg: RunConfig, outcome: Outcome, reason: str
) -> Result:
    """Build a zero-duration ``Result`` for terminal non-gradeable outcomes.

    Used for NOT_ATTEMPTED (container never started) and ERRORED (grading
    harness failure). The two callers differ only in ``outcome``.
    """
    return Result(
        workflow_slug=ref.slug,
        workflow_token=ref.token,
        task_id=task.task_id,
        outcome=outcome,
        model=cfg.model,
        duration_sec=0.0,
        reason=reason,
        artifacts_dir=f"tasks/{task.task_id}/{ref.slug}",
    )


def _assemble_result(
    task: Task, ref: WorkflowRef, cfg: RunConfig, agent: AgentOutcome,
    grading: grader.GradingOutcome,
) -> Result:
    """Classify the outcome and assemble the per-task ``Result`` (FR-019/020).

    An agent timeout or a verifier crash classifies as ERRORED. A non-zero agent
    exit that still produced a gradeable change is classified by the reward (it may
    still pass), so it is not forced to ERRORED here.
    """
    outcome, reason = classify_outcome(
        reward=grading.reward,
        agent_failed=agent.timed_out,
        verifier_failed=grading.crashed,
    )
    tokens, cost = parse_agent_usage(agent.stdout)
    rel = f"tasks/{task.task_id}/{ref.slug}"
    return Result(
        workflow_slug=ref.slug,
        workflow_token=ref.token,
        task_id=task.task_id,
        outcome=outcome,
        model=cfg.model,
        reward=grading.reward,
        duration_sec=agent.duration_sec,
        grading_duration_sec=grading.duration_sec,
        agent_exit_code=agent.exit_code,
        verifier_exit_code=grading.verifier_exit_code,
        tokens=tokens,
        cost_usd=cost,
        reason=reason,
        patch_present=grading.patch_present,
        artifacts_dir=rel,
    )


def run_task(
    task: Task, cfg: RunConfig, ref: WorkflowRef, runtime_dir: Path, config_dir: Path,
    docker: DockerCli,
) -> Result:
    """Run the agent phase, grade, classify, and persist artifacts for one task.

    The container is force-removed in a ``finally`` regardless of outcome. A
    provisioning failure yields NOT_ATTEMPTED; an agent timeout yields ERRORED but
    grading is still attempted to capture any partial change. ``result.json`` is always
    written.
    """
    artifacts_dir = _task_artifacts_dir(cfg.run_dir, task.task_id, ref.slug)
    container_id: Optional[str] = None
    try:
        agent = agent_runner.run_agent(
            task, ref, cfg.credential, cfg.model, runtime_dir, config_dir, docker
        )
        container_id = agent.container_id
        _write_agent_artifacts(artifacts_dir, agent)
        grading = grader.grade(container_id, task, artifacts_dir, docker)
        write_text_file(artifacts_dir / config.VERIFIER_LOG, grading.verifier_log)
        _write_reward_file(artifacts_dir, grading.reward)
        result = _assemble_result(task, ref, cfg, agent, grading)
    except AgentError as exc:
        logger.warning("Task '%s': not attempted: %s", task.task_id, exc)
        result = _terminal_result(task, ref, cfg, Outcome.NOT_ATTEMPTED, str(exc))
    except GradingError as exc:
        logger.warning("Task '%s': grading could not run: %s", task.task_id, exc)
        result = _terminal_result(task, ref, cfg, Outcome.ERRORED, str(exc))
    finally:
        if container_id is not None:
            docker.rm_force(container_id)
    write_json_file(artifacts_dir / config.RESULT_JSON, result.to_dict())
    return result


def _write_reward_file(artifacts_dir: Path, reward: Optional[float]) -> None:
    """Persist the raw reward to ``reward.txt`` (empty when no reward was produced)."""
    text = "" if reward is None else str(reward)
    write_text_file(artifacts_dir / config.REWARD_FILENAME, text)


def _selection_dict(selection: Selection) -> dict:
    """Serialize a ``Selection`` for embedding in run/comparison JSON."""
    return {
        "mode": selection.mode,
        "n": selection.n,
        "seed": selection.seed,
        "task_ids": list(selection.task_ids),
    }


def _run_one_task(
    task_id: str, tasks: dict[str, Task], cfg: RunConfig, ref: WorkflowRef,
    runtime_dir: Path, config_dir: Path, docker: DockerCli,
) -> Result:
    """Run one selected task, recording any unexpected failure as ERRORED (NFR-005).

    A task missing from the corpus is NOT_ATTEMPTED. An unexpected exception is caught
    here so a single task's failure never aborts the batch.
    """
    task = tasks.get(task_id)
    if task is None:
        logger.warning("Selected task '%s' not in corpus; recording not_attempted.", task_id)
        return _missing_task_result(task_id, ref, cfg)
    try:
        return run_task(task, cfg, ref, runtime_dir, config_dir, docker)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Deliberate last-resort guard (NFR-005): one task's unexpected failure must
        # never abort the batch. The full traceback is logged; the task is errored.
        logger.exception("Task '%s': unexpected failure; recording errored.", task_id)
        return _terminal_result(task, ref, cfg, Outcome.ERRORED, f"unexpected harness error: {exc}")


def run_workflow(
    cfg: RunConfig, ref: WorkflowRef, tasks: dict[str, Task], runtime_dir: Path,
    config_dir: Path, docker: DockerCli, started_at: str = "", finished_at: str = "",
) -> Run:
    """Run one workflow over the resolved selection sequentially (continue-on-failure).

    Tasks selected but absent from ``tasks`` are recorded NOT_ATTEMPTED. Returns a
    built ``Run`` with counts and pass rate.
    """
    logger.info("Running workflow %s over %d task(s)", ref.token, len(cfg.selection.task_ids))
    results = [
        _run_one_task(task_id, tasks, cfg, ref, runtime_dir, config_dir, docker)
        for task_id in cfg.selection.task_ids
    ]
    return build_run(
        run_id=cfg.run_id,
        workflow_slug=ref.slug,
        workflow_token=ref.token,
        model=cfg.model,
        selection=_selection_dict(cfg.selection),
        results=results,
        started_at=started_at,
        finished_at=finished_at,
    )


def _missing_task_result(task_id: str, ref: WorkflowRef, cfg: RunConfig) -> Result:
    """Build a NOT_ATTEMPTED ``Result`` for a selected id missing from the corpus."""
    return Result(
        workflow_slug=ref.slug,
        workflow_token=ref.token,
        task_id=task_id,
        outcome=Outcome.NOT_ATTEMPTED,
        model=cfg.model,
        duration_sec=0.0,
        reason="task id not present in corpus",
        artifacts_dir=f"tasks/{task_id}/{ref.slug}",
    )


def run_comparison(
    cfg: RunConfig, tasks: dict[str, Task], runtime_dir: Path, config_dir: Path, docker: DockerCli,
) -> Comparison:
    """Run every workflow over the IDENTICAL selection, then build a comparison (FR-021).

    Each workflow's run is written as ``run-<slug>.json`` / ``report-<slug>.md`` under the
    run dir; the aggregate comparison is built from the per-workflow runs. The same
    ``cfg.selection`` and ``cfg.model`` apply to every workflow (NFR-002).
    """
    runs: list[Run] = []
    for ref in cfg.workflows:
        run = run_workflow(cfg, ref, tasks, runtime_dir, config_dir, docker)
        report.write_run(run, cfg.run_dir, slug_suffix=True)
        runs.append(run)

    return build_comparison(
        run_id=cfg.run_id,
        model=cfg.model,
        selection=_selection_dict(cfg.selection),
        runs=runs,
    )
