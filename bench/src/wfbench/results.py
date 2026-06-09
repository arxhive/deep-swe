"""Outcome model, result/run/comparison entities, and the pure aggregation math.

This module is the primary unit-test surface (SC-002/SC-006). Serializers emit
snake_case JSON, render ``Outcome`` as its string value, and NEVER include any
credential value. All aggregation is pure (no I/O).
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


class Outcome(str, Enum):
    """The single outcome state for one workflow on one task (FR-020)."""

    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"
    NOT_ATTEMPTED = "not_attempted"


# Outcomes that count toward the ``attempted`` denominator.
_ATTEMPTED_OUTCOMES = (Outcome.PASSED, Outcome.FAILED, Outcome.ERRORED)


@dataclass
class Result:
    """The outcome of one workflow on one task (FR-019). Serialized to result.json."""

    workflow_slug: str
    workflow_token: str
    task_id: str
    outcome: Outcome
    model: str
    duration_sec: float
    reward: Optional[float] = None
    grading_duration_sec: Optional[float] = None
    agent_exit_code: Optional[int] = None
    verifier_exit_code: Optional[int] = None
    tokens: Optional[dict] = None
    cost_usd: Optional[float] = None
    reason: Optional[str] = None
    patch_present: bool = False
    artifacts_dir: str = ""

    def to_dict(self) -> dict:
        """Serialize to a snake_case JSON-ready dict (never includes a credential)."""
        return {
            "workflow_slug": self.workflow_slug,
            "workflow_token": self.workflow_token,
            "task_id": self.task_id,
            "outcome": self.outcome.value,
            "model": self.model,
            "reward": self.reward,
            "duration_sec": self.duration_sec,
            "grading_duration_sec": self.grading_duration_sec,
            "agent_exit_code": self.agent_exit_code,
            "verifier_exit_code": self.verifier_exit_code,
            "tokens": self.tokens,
            "cost_usd": self.cost_usd,
            "reason": self.reason,
            "patch_present": self.patch_present,
            "artifacts_dir": self.artifacts_dir,
        }


@dataclass
class Run:
    """One workflow over the subset (FR-020). Serialized to run.json."""

    run_id: str
    workflow_slug: str
    workflow_token: str
    model: str
    selection: dict
    results: list[Result] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    pass_rate: float = 0.0
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict:
        """Serialize the run and its results to a JSON-ready dict."""
        return {
            "run_id": self.run_id,
            "workflow_token": self.workflow_token,
            "workflow_slug": self.workflow_slug,
            "model": self.model,
            "selection": self.selection,
            "counts": self.counts,
            "pass_rate": self.pass_rate,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass
class Comparison:
    """Two-plus workflows over one identical subset (FR-021). Serialized to comparison.json."""

    run_id: str
    model: str
    selection: dict
    runs: list[Run] = field(default_factory=list)
    common_attempted_ids: list[str] = field(default_factory=list)
    per_workflow: list[dict] = field(default_factory=list)
    matrix: list[dict] = field(default_factory=list)
    ranking: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize the comparison summary to a JSON-ready dict."""
        return {
            "run_id": self.run_id,
            "model": self.model,
            "selection": self.selection,
            "common_attempted_ids": self.common_attempted_ids,
            "per_workflow": self.per_workflow,
            "matrix": self.matrix,
            "ranking": self.ranking,
        }


def classify_outcome(
    reward: Optional[float],
    provisioning_failed: bool = False,
    agent_failed: bool = False,
    verifier_failed: bool = False,
) -> tuple[Outcome, Optional[str]]:
    """Classify a task attempt into an ``Outcome`` plus a reason string (R10).

    Precedence: provisioning failure -> NOT_ATTEMPTED; agent/verifier crash or a
    missing reward -> ERRORED; reward == 1 -> PASSED; any other present reward ->
    FAILED. ``reason`` is None only for a clean pass.
    """
    if provisioning_failed:
        return Outcome.NOT_ATTEMPTED, "task could not be provisioned"
    if agent_failed:
        return Outcome.ERRORED, "agent run failed or timed out"
    if verifier_failed:
        return Outcome.ERRORED, "verifier crashed"
    if reward is None:
        return Outcome.ERRORED, "no reward produced by the verifier"
    if reward == 1:
        return Outcome.PASSED, None
    return Outcome.FAILED, f"verifier reward was {reward}, not a pass"


def _count_outcomes(results: Sequence[Result]) -> dict:
    """Return the counts dict (selected/attempted/passed/failed/errored/not_attempted)."""
    passed = sum(1 for r in results if r.outcome is Outcome.PASSED)
    failed = sum(1 for r in results if r.outcome is Outcome.FAILED)
    errored = sum(1 for r in results if r.outcome is Outcome.ERRORED)
    not_attempted = sum(1 for r in results if r.outcome is Outcome.NOT_ATTEMPTED)
    return {
        "selected": len(results),
        "attempted": passed + failed + errored,
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "not_attempted": not_attempted,
    }


def build_run(
    run_id: str,
    workflow_slug: str,
    workflow_token: str,
    model: str,
    selection: dict,
    results: Sequence[Result],
    started_at: str = "",
    finished_at: str = "",
) -> Run:
    """Build a ``Run`` with counts and ``pass_rate = passed / attempted`` (FR-020).

    ``pass_rate`` is 0.0 when nothing was attempted.
    """
    counts = _count_outcomes(results)
    attempted = counts["attempted"]
    pass_rate = counts["passed"] / attempted if attempted else 0.0
    return Run(
        run_id=run_id,
        workflow_slug=workflow_slug,
        workflow_token=workflow_token,
        model=model,
        selection=selection,
        results=list(results),
        counts=counts,
        pass_rate=pass_rate,
        started_at=started_at,
        finished_at=finished_at,
    )


def _attempted_ids(run: Run) -> set[str]:
    """Return the set of task ids the run actually attempted."""
    return {r.task_id for r in run.results if r.outcome in _ATTEMPTED_OUTCOMES}


def _passed_ids(run: Run) -> set[str]:
    """Return the set of task ids the run passed."""
    return {r.task_id for r in run.results if r.outcome is Outcome.PASSED}


def _common_attempted(runs: Sequence[Run]) -> list[str]:
    """Return the sorted intersection of task ids every run attempted."""
    if not runs:
        return []
    common = _attempted_ids(runs[0])
    for run in runs[1:]:
        common &= _attempted_ids(run)
    return sorted(common)


def result_total_tokens(result: Result) -> Optional[int]:
    """Return one attempt's total tokens (input + output), or None when unknown.

    Prefers the precomputed ``total`` field; otherwise sums whichever of input/output
    token counts are present. Cache tokens are excluded (they are reused context, not
    new generation). None means the agent reported no usage (e.g. an early error).
    """
    tokens = result.tokens
    if not isinstance(tokens, dict):
        return None
    if isinstance(tokens.get("total"), int):
        return tokens["total"]
    have_input = isinstance(tokens.get("input_tokens"), int)
    have_output = isinstance(tokens.get("output_tokens"), int)
    if have_input or have_output:
        return tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)
    return None


def _per_workflow_stats(run: Run, common_ids: Sequence[str]) -> dict:
    """Return one workflow's own and common-attempted pass rates, counts, and totals."""
    common_set = set(common_ids)
    passed = _passed_ids(run)
    common_passed = len(passed & common_set)
    common_rate = common_passed / len(common_set) if common_set else 0.0
    token_values = [result_total_tokens(r) for r in run.results]
    return {
        "workflow_slug": run.workflow_slug,
        "pass_rate": run.pass_rate,
        "common_attempted_pass_rate": common_rate,
        "counts": run.counts,
        "total_duration_sec": sum(r.duration_sec for r in run.results),
        "total_tokens": sum(value for value in token_values if value is not None),
    }


def _build_matrix(runs: Sequence[Run], selection_ids: Sequence[str]) -> list[dict]:
    """Return the per-task outcome matrix across all workflows (FR-022)."""
    by_run = {run.workflow_slug: {r.task_id: r.outcome.value for r in run.results} for run in runs}
    matrix = []
    for task_id in selection_ids:
        outcomes = {slug: outcomes_map.get(task_id) for slug, outcomes_map in by_run.items()}
        matrix.append({"task_id": task_id, "outcomes": outcomes})
    return matrix


def _rank(per_workflow: Sequence[dict]) -> list[str]:
    """Rank workflow slugs by common-attempted pass rate, then own rate, then slug."""
    ordered = sorted(
        per_workflow,
        key=lambda stats: (
            -stats["common_attempted_pass_rate"],
            -stats["pass_rate"],
            stats["workflow_slug"],
        ),
    )
    return [stats["workflow_slug"] for stats in ordered]


def build_comparison(
    run_id: str, model: str, selection: dict, runs: Sequence[Run]
) -> Comparison:
    """Build a ``Comparison`` over runs sharing one identical subset (FR-021/022).

    Computes the common-attempted intersection, per-workflow own and common-attempted
    pass rates, the per-task outcome matrix, and the ranking. An empty common set is
    logged as not-comparable and yields 0.0 common rates.
    """
    common_ids = _common_attempted(runs)
    if not common_ids:
        logger.warning("Common-attempted set is empty; comparison ranking is not meaningful.")

    per_workflow = [_per_workflow_stats(run, common_ids) for run in runs]
    selection_ids = list(selection.get("task_ids", []))
    matrix = _build_matrix(runs, selection_ids)
    ranking = _rank(per_workflow)
    return Comparison(
        run_id=run_id,
        model=model,
        selection=selection,
        runs=list(runs),
        common_attempted_ids=common_ids,
        per_workflow=per_workflow,
        matrix=matrix,
        ranking=ranking,
    )
