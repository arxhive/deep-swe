"""Unit tests for run/comparison reporting (FR-023/028, NFR-004 security)."""

import json
from pathlib import Path

from wfbench.report import print_summary, write_comparison, write_run
from wfbench.results import Outcome, Result, build_comparison, build_run


def _result(task_id: str, outcome: Outcome, slug: str = "somecode", reward=None) -> Result:
    """Build a Result with optional reward for reporting tests."""
    return Result(
        workflow_slug=slug,
        workflow_token=f"/{slug}",
        task_id=task_id,
        outcome=outcome,
        model="claude-opus-4-8",
        duration_sec=12.3,
        reward=reward,
    )


def _single_run():
    """Build a single Run with a mix of outcomes for reporting tests."""
    results = [
        _result("alpha-task", Outcome.PASSED, reward=1.0),
        _result("beta-task", Outcome.FAILED, reward=0.0),
    ]
    return build_run("20260607T000000Z-abc123", "somecode", "/somecode", "claude-opus-4-8",
                     {"mode": "explicit", "n": None, "seed": None, "task_ids": ["alpha-task", "beta-task"]},
                     results)


def test_write_run_emits_valid_json_matching_shape(tmp_path: Path):
    """run.json is valid JSON carrying the data-model Run fields."""
    run = _single_run()
    write_run(run, tmp_path)

    data = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert data["run_id"] == run.run_id
    assert data["workflow_token"] == "/somecode"
    assert data["pass_rate"] == 0.5
    assert set(data["counts"]) == {"selected", "attempted", "passed", "failed", "errored", "not_attempted"}
    assert {r["task_id"] for r in data["results"]} == {"alpha-task", "beta-task"}


def test_write_run_markdown_has_pass_rate_and_every_task(tmp_path: Path):
    """report.md contains the pass rate and a row for every task."""
    run = _single_run()
    write_run(run, tmp_path)

    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "50.0%" in text
    assert "alpha-task" in text
    assert "beta-task" in text


def test_no_credential_value_in_outputs(tmp_path: Path):
    """A credential-like value never appears in any written artifact (NFR-004)."""
    run = _single_run()
    write_run(run, tmp_path)

    for name in ("run.json", "report.md"):
        content = (tmp_path / name).read_text(encoding="utf-8")
        assert "sk-" not in content
        assert "oat-" not in content


def test_print_summary_includes_run_dir(tmp_path: Path, capsys):
    """print_summary prints the pass rate and the artifacts directory (FR-028)."""
    run = _single_run()
    print_summary(run, tmp_path)

    out = capsys.readouterr().out
    assert "50.0%" in out
    assert str(tmp_path) in out


def _comparison():
    """Build a Comparison of two workflows over the same two-task subset."""
    selection_ids = ["alpha-task", "beta-task"]
    selection = {"mode": "explicit", "n": None, "seed": None, "task_ids": selection_ids}
    run_a = build_run("r", "somecode", "/somecode", "m", selection, [
        _result("alpha-task", Outcome.PASSED, "somecode", 1.0),
        _result("beta-task", Outcome.FAILED, "somecode", 0.0),
    ])
    run_b = build_run("r", "story-to-live", "/story-to-live", "m", selection, [
        _result("alpha-task", Outcome.FAILED, "story-to-live", 0.0),
        _result("beta-task", Outcome.PASSED, "story-to-live", 1.0),
    ])
    return build_comparison("r", "m", selection, [run_a, run_b])


def test_write_comparison_matrix_shows_each_outcome(tmp_path: Path):
    """comparison.md/json carry the per-task matrix with each workflow's outcome."""
    comparison = _comparison()
    write_comparison(comparison, tmp_path)

    data = json.loads((tmp_path / "comparison.json").read_text(encoding="utf-8"))
    rows = {row["task_id"]: row["outcomes"] for row in data["matrix"]}
    assert rows["alpha-task"] == {"somecode": "passed", "story-to-live": "failed"}

    md = (tmp_path / "comparison.md").read_text(encoding="utf-8")
    assert "alpha-task" in md and "story-to-live" in md


def test_comparison_partial_failure_ranks_over_common_set(tmp_path: Path):
    """A partially-failing workflow still ranks over the common-attempted set."""
    selection_ids = ["alpha-task", "beta-task"]
    selection = {"mode": "explicit", "n": None, "seed": None, "task_ids": selection_ids}
    # 'a' attempts both and passes both; 'b' fails to provision beta-task.
    run_a = build_run("r", "a", "/a", "m", selection, [
        _result("alpha-task", Outcome.PASSED, "a", 1.0),
        _result("beta-task", Outcome.PASSED, "a", 1.0),
    ])
    run_b = build_run("r", "b", "/b", "m", selection, [
        _result("alpha-task", Outcome.FAILED, "b", 0.0),
        _result("beta-task", Outcome.NOT_ATTEMPTED, "b"),
    ])
    comparison = build_comparison("r", "m", selection, [run_a, run_b])

    # Common set is {alpha-task}; 'a' passed it, 'b' failed it -> a ranks first.
    assert comparison.common_attempted_ids == ["alpha-task"]
    assert comparison.ranking == ["a", "b"]


def test_comparison_empty_common_reported_not_comparable(tmp_path: Path):
    """An empty common-attempted set is reported as not-comparable in the Markdown."""
    selection_ids = ["alpha-task", "beta-task"]
    selection = {"mode": "explicit", "n": None, "seed": None, "task_ids": selection_ids}
    run_a = build_run("r", "a", "/a", "m", selection, [
        _result("alpha-task", Outcome.PASSED, "a", 1.0),
        _result("beta-task", Outcome.NOT_ATTEMPTED, "a"),
    ])
    run_b = build_run("r", "b", "/b", "m", selection, [
        _result("alpha-task", Outcome.NOT_ATTEMPTED, "b"),
        _result("beta-task", Outcome.PASSED, "b", 1.0),
    ])
    comparison = build_comparison("r", "m", selection, [run_a, run_b])
    write_comparison(comparison, tmp_path)

    assert comparison.common_attempted_ids == []
    assert "not comparable" in (tmp_path / "comparison.md").read_text(encoding="utf-8").lower()


def test_print_summary_comparison_includes_ranking_and_each_workflow(capsys, tmp_path: Path):
    """print_summary for a Comparison prints the ranking and each workflow's pass rate (FR-028)."""
    comparison = _comparison()
    print_summary(comparison, tmp_path)

    out = capsys.readouterr().out
    assert "somecode" in out
    assert "story-to-live" in out
    assert "ranking" in out.lower() or any(wf in out for wf in ("somecode", "story-to-live"))
    assert str(tmp_path) in out


def _timed_result(task_id, outcome, slug, reward, duration, total_tokens) -> Result:
    """Build a Result with explicit duration and total tokens for cost-summary tests."""
    tokens = None if total_tokens is None else {"total": total_tokens}
    return Result(
        workflow_slug=slug, workflow_token=f"/{slug}", task_id=task_id, outcome=outcome,
        model="m", duration_sec=duration, reward=reward, tokens=tokens,
    )


def test_comparison_md_and_json_carry_duration_and_token_totals(tmp_path: Path):
    """comparison.md adds per-task duration + token tables with per-workflow totals,
    and comparison.json carries the same totals per workflow."""
    selection_ids = ["alpha-task", "beta-task"]
    selection = {"mode": "explicit", "n": None, "seed": None, "task_ids": selection_ids}
    run_a = build_run("r", "a", "/a", "m", selection, [
        _timed_result("alpha-task", Outcome.PASSED, "a", 1.0, 2.0, 111),
        _timed_result("beta-task", Outcome.FAILED, "a", 0.0, 3.0, 222),
    ])
    run_b = build_run("r", "b", "/b", "m", selection, [
        _timed_result("alpha-task", Outcome.FAILED, "b", 0.0, 10.0, 1111),
        _timed_result("beta-task", Outcome.PASSED, "b", 1.0, 20.0, 2222),
    ])
    comparison = build_comparison("r", "m", selection, [run_a, run_b])
    write_comparison(comparison, tmp_path)

    md = (tmp_path / "comparison.md").read_text(encoding="utf-8")
    assert "Duration per task" in md and "Tokens per task" in md
    assert "| **Total** |" in md
    assert "5.0" in md and "30.0" in md      # per-workflow duration totals
    assert "333" in md and "3,333" in md     # per-workflow token totals (comma-formatted)

    data = json.loads((tmp_path / "comparison.json").read_text(encoding="utf-8"))
    stats = {s["workflow_slug"]: s for s in data["per_workflow"]}
    assert stats["a"]["total_duration_sec"] == 5.0
    assert stats["a"]["total_tokens"] == 333
    assert stats["b"]["total_duration_sec"] == 30.0
    assert stats["b"]["total_tokens"] == 3333


def test_write_run_slug_suffix_names_files_per_workflow(tmp_path: Path):
    """write_run with slug_suffix=True writes workflow-slug-named files (FR-023 comparison sub-runs)."""
    run = _single_run()
    write_run(run, tmp_path, slug_suffix=True)

    assert (tmp_path / "run-somecode.json").exists()
    assert (tmp_path / "report-somecode.md").exists()
    assert not (tmp_path / "run.json").exists()
    assert not (tmp_path / "report.md").exists()
