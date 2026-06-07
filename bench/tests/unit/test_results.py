"""Unit tests for outcome classification and pass-rate / comparison math (SC-006)."""

from wfbench.results import (
    Outcome,
    Result,
    build_comparison,
    build_run,
    classify_outcome,
)


def _result(task_id: str, outcome: Outcome, slug: str = "wf") -> Result:
    """Build a minimal Result for aggregation tests."""
    return Result(
        workflow_slug=slug,
        workflow_token=f"/{slug}",
        task_id=task_id,
        outcome=outcome,
        model="m",
        duration_sec=1.0,
    )


def test_classify_passed_on_reward_one() -> None:
    """Reward exactly 1 classifies as PASSED with no reason."""
    outcome, reason = classify_outcome(1.0)
    assert outcome is Outcome.PASSED
    assert reason is None


def test_classify_failed_on_reward_zero() -> None:
    """A present non-pass reward classifies as FAILED with a reason."""
    outcome, reason = classify_outcome(0.0)
    assert outcome is Outcome.FAILED
    assert reason


def test_classify_errored_on_missing_reward() -> None:
    """A missing reward classifies as ERRORED."""
    outcome, reason = classify_outcome(None)
    assert outcome is Outcome.ERRORED
    assert reason


def test_classify_errored_on_agent_or_verifier_failure() -> None:
    """Agent timeout and verifier crash both classify as ERRORED."""
    assert classify_outcome(None, agent_failed=True)[0] is Outcome.ERRORED
    assert classify_outcome(1.0, verifier_failed=True)[0] is Outcome.ERRORED


def test_classify_not_attempted_on_provisioning_failure() -> None:
    """A provisioning failure classifies as NOT_ATTEMPTED regardless of reward."""
    outcome, reason = classify_outcome(None, provisioning_failed=True)
    assert outcome is Outcome.NOT_ATTEMPTED
    assert reason


def test_build_run_counts_and_pass_rate() -> None:
    """build_run computes counts and pass_rate = passed / attempted."""
    results = [
        _result("t1", Outcome.PASSED),
        _result("t2", Outcome.PASSED),
        _result("t3", Outcome.FAILED),
        _result("t4", Outcome.ERRORED),
        _result("t5", Outcome.NOT_ATTEMPTED),
    ]
    run = build_run("r1", "wf", "/wf", "m", {"task_ids": []}, results)

    # attempted = passed + failed + errored = 4; not_attempted is excluded.
    assert run.counts == {
        "selected": 5,
        "attempted": 4,
        "passed": 2,
        "failed": 1,
        "errored": 1,
        "not_attempted": 1,
    }
    assert run.pass_rate == 0.5


def test_build_run_pass_rate_zero_when_nothing_attempted() -> None:
    """pass_rate is 0.0 when attempted == 0 (no division by zero)."""
    run = build_run("r1", "wf", "/wf", "m", {}, [_result("t1", Outcome.NOT_ATTEMPTED)])
    assert run.counts["attempted"] == 0
    assert run.pass_rate == 0.0


def _run_for(slug: str, outcomes: dict, selection_ids: list[str]):
    """Build a Run for a workflow from a {task_id: Outcome} mapping."""
    results = [_result(tid, outcome, slug=slug) for tid, outcome in outcomes.items()]
    return build_run("r1", slug, f"/{slug}", "m", {"task_ids": selection_ids}, results)


def test_build_comparison_common_attempted_and_ranking() -> None:
    """Common-attempted is the intersection of attempted ids; ranking uses it."""
    selection_ids = ["t1", "t2", "t3"]
    run_a = _run_for("a", {"t1": Outcome.PASSED, "t2": Outcome.PASSED, "t3": Outcome.NOT_ATTEMPTED}, selection_ids)
    run_b = _run_for("b", {"t1": Outcome.FAILED, "t2": Outcome.PASSED, "t3": Outcome.PASSED}, selection_ids)

    comparison = build_comparison("r1", "m", {"task_ids": selection_ids}, [run_a, run_b])

    # t3 was not attempted by 'a', so the common set is {t1, t2}.
    assert comparison.common_attempted_ids == ["t1", "t2"]
    # 'a' passed both common tasks (1.0); 'b' passed one of two (0.5) -> a ranks first.
    assert comparison.ranking == ["a", "b"]
    per_a = next(p for p in comparison.per_workflow if p["workflow_slug"] == "a")
    assert per_a["common_attempted_pass_rate"] == 1.0


def test_build_comparison_matrix_has_every_task_and_workflow() -> None:
    """The matrix carries each selected task with every workflow's outcome (FR-022)."""
    selection_ids = ["t1", "t2"]
    run_a = _run_for("a", {"t1": Outcome.PASSED, "t2": Outcome.FAILED}, selection_ids)
    run_b = _run_for("b", {"t1": Outcome.FAILED, "t2": Outcome.PASSED}, selection_ids)

    comparison = build_comparison("r1", "m", {"task_ids": selection_ids}, [run_a, run_b])

    rows = {row["task_id"]: row["outcomes"] for row in comparison.matrix}
    assert rows["t1"] == {"a": "passed", "b": "failed"}
    assert rows["t2"] == {"a": "failed", "b": "passed"}


def test_build_comparison_empty_common_set_is_handled() -> None:
    """An empty common-attempted set yields 0.0 common rates (not-comparable edge)."""
    selection_ids = ["t1", "t2"]
    run_a = _run_for("a", {"t1": Outcome.PASSED, "t2": Outcome.NOT_ATTEMPTED}, selection_ids)
    run_b = _run_for("b", {"t1": Outcome.NOT_ATTEMPTED, "t2": Outcome.PASSED}, selection_ids)

    comparison = build_comparison("r1", "m", {"task_ids": selection_ids}, [run_a, run_b])

    assert comparison.common_attempted_ids == []
    for stats in comparison.per_workflow:
        assert stats["common_attempted_pass_rate"] == 0.0


def test_result_to_dict_serializes_outcome_value_and_no_credential() -> None:
    """to_dict emits the outcome string value and never a credential field."""
    data = _result("t1", Outcome.PASSED).to_dict()
    assert data["outcome"] == "passed"
    assert "credential" not in data
    assert "value" not in data


def test_errored_before_edit_result_serializes_and_tallies() -> None:
    """An errored-before-edit attempt serializes with patch_present False + a reason,
    and still counts in the run tally (SC-004/SC-006)."""
    errored = Result(
        workflow_slug="wf",
        workflow_token="/wf",
        task_id="t1",
        outcome=Outcome.ERRORED,
        model="m",
        duration_sec=2.0,
        reward=None,
        reason="agent run failed or timed out",
        patch_present=False,
    )
    data = errored.to_dict()
    assert data["outcome"] == "errored"
    assert data["patch_present"] is False
    assert data["reason"]

    run = build_run("r1", "wf", "/wf", "m", {}, [errored, _result("t2", Outcome.PASSED)])
    # The errored attempt is attempted (denominator) but not a pass.
    assert run.counts["attempted"] == 2
    assert run.counts["errored"] == 1
    assert run.pass_rate == 0.5
