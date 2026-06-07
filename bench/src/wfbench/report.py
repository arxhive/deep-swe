"""Run and comparison reporting: machine-readable JSON + human-readable Markdown (FR-023/028).

Paths are serialized run-relative (never absolute host paths) for artifact portability.
The at-a-glance summary prints to stdout; structured progress logs go to stderr.
"""

import logging
from pathlib import Path

from . import config
from .results import Comparison, Run
from .write_artifacts import write_json_file, write_text_file

logger = logging.getLogger(__name__)


def _format_rate(rate: float) -> str:
    """Format a pass rate as a percentage with one decimal place."""
    return f"{rate * 100:.1f}%"


def _run_table(run: Run) -> str:
    """Render the per-task outcome table for a single run as Markdown."""
    header = "| Task | Outcome | Reward | Duration (s) | Patch | Reason |\n"
    header += "|------|---------|--------|--------------|-------|--------|\n"
    rows = []
    for result in run.results:
        reward = "-" if result.reward is None else f"{result.reward:g}"
        reason = result.reason or ""
        patch = "yes" if result.patch_present else "no"
        rows.append(
            f"| {result.task_id} | {result.outcome.value} | {reward} | "
            f"{result.duration_sec:.1f} | {patch} | {reason} |"
        )
    return header + "\n".join(rows) + "\n"


def _run_markdown(run: Run) -> str:
    """Render the full single-run Markdown report."""
    counts = run.counts
    lines = [
        f"# Workflow Bench run `{run.run_id}`",
        "",
        f"- Workflow: `{run.workflow_token}`",
        f"- Model: `{run.model}`",
        f"- Pass rate: **{_format_rate(run.pass_rate)}** "
        f"({counts['passed']}/{counts['attempted']} attempted)",
        f"- Selected: {counts['selected']} | attempted: {counts['attempted']} | "
        f"not attempted: {counts['not_attempted']} | passed: {counts['passed']} | "
        f"failed: {counts['failed']} | errored: {counts['errored']}",
        "",
        "## Per-task outcomes",
        "",
        _run_table(run),
    ]
    return "\n".join(lines)


def write_run(run: Run, run_dir: Path, slug_suffix: bool = False) -> None:
    """Write ``run.json`` and ``report.md`` for a single run under ``run_dir``.

    When ``slug_suffix`` is True (comparison sub-runs), file names carry the workflow
    slug so multiple workflows under one run dir never collide.
    """
    json_name = f"run-{run.workflow_slug}.json" if slug_suffix else config.RUN_JSON
    md_name = f"report-{run.workflow_slug}.md" if slug_suffix else config.REPORT_MD
    write_json_file(run_dir / json_name, run.to_dict())
    write_text_file(run_dir / md_name, _run_markdown(run))
    logger.info("Wrote run report for %s to %s", run.workflow_token, run_dir / md_name)


def _comparison_matrix_table(comparison: Comparison) -> str:
    """Render the per-task outcome matrix across workflows as a Markdown table."""
    slugs = [run.workflow_slug for run in comparison.runs]
    header = "| Task | " + " | ".join(slugs) + " |\n"
    header += "|------|" + "|".join(["---"] * len(slugs)) + "|\n"
    rows = []
    for row in comparison.matrix:
        cells = [row["outcomes"].get(slug) or "-" for slug in slugs]
        rows.append(f"| {row['task_id']} | " + " | ".join(cells) + " |")
    return header + "\n".join(rows) + "\n"


def _comparison_per_workflow_table(comparison: Comparison) -> str:
    """Render the per-workflow pass-rate table for a comparison."""
    header = "| Workflow | Pass rate | Common-attempted rate | Passed/Attempted |\n"
    header += "|----------|-----------|-----------------------|------------------|\n"
    rows = []
    for stats in comparison.per_workflow:
        counts = stats["counts"]
        rows.append(
            f"| {stats['workflow_slug']} | {_format_rate(stats['pass_rate'])} | "
            f"{_format_rate(stats['common_attempted_pass_rate'])} | "
            f"{counts['passed']}/{counts['attempted']} |"
        )
    return header + "\n".join(rows) + "\n"


def _comparison_markdown(comparison: Comparison) -> str:
    """Render the full comparison Markdown report."""
    common = comparison.common_attempted_ids
    common_line = (
        f"- Common-attempted tasks: {len(common)} ({', '.join(common)})"
        if common
        else "- Common-attempted tasks: 0 (not comparable - no task attempted by all workflows)"
    )
    lines = [
        f"# Workflow Bench comparison `{comparison.run_id}`",
        "",
        f"- Model: `{comparison.model}`",
        f"- Ranking (by common-attempted pass rate): {', '.join(comparison.ranking)}",
        common_line,
        "",
        "## Per-workflow pass rates",
        "",
        _comparison_per_workflow_table(comparison),
        "## Per-task outcome matrix",
        "",
        _comparison_matrix_table(comparison),
    ]
    return "\n".join(lines)


def write_comparison(comparison: Comparison, run_dir: Path) -> None:
    """Write ``comparison.json`` and ``comparison.md`` under ``run_dir`` (FR-021/022)."""
    write_json_file(run_dir / config.COMPARISON_JSON, comparison.to_dict())
    write_text_file(run_dir / config.COMPARISON_MD, _comparison_markdown(comparison))
    logger.info("Wrote comparison report to %s", run_dir / config.COMPARISON_MD)


def print_summary(run_or_comparison, run_dir: Path) -> None:
    """Print an at-a-glance summary to stdout (FR-028).

    Accepts a ``Run`` (single run) or a ``Comparison`` (multi-workflow) and prints the
    pass rate(s) plus the artifacts path.
    """
    if isinstance(run_or_comparison, Comparison):
        _print_comparison_summary(run_or_comparison, run_dir)
    else:
        _print_run_summary(run_or_comparison, run_dir)


def _print_run_summary(run: Run, run_dir: Path) -> None:
    """Print the single-run stdout summary."""
    counts = run.counts
    print(f"Workflow {run.workflow_token}: pass rate {_format_rate(run.pass_rate)} "
          f"({counts['passed']}/{counts['attempted']} attempted, "
          f"{counts['not_attempted']} not attempted)")
    print(f"Artifacts: {run_dir}")


def _print_comparison_summary(comparison: Comparison, run_dir: Path) -> None:
    """Print the multi-workflow stdout summary."""
    print(f"Comparison over {len(comparison.runs)} workflows "
          f"(ranking: {', '.join(comparison.ranking)}):")
    for stats in comparison.per_workflow:
        print(f"  {stats['workflow_slug']}: pass rate {_format_rate(stats['pass_rate'])}, "
              f"common-attempted {_format_rate(stats['common_attempted_pass_rate'])}")
    print(f"Artifacts: {run_dir}")
