"""Unit tests for CLI parsing and dispatch (no docker, no containers)."""

import re
from pathlib import Path

import pytest

from wfbench import cli
from wfbench.errors import WfbenchError
from wfbench.preflight import Credential, CredentialKind
from wfbench.results import Outcome, Result, build_comparison, build_run
from wfbench.selection import Selection


@pytest.fixture
def stub_pipeline(monkeypatch, synthetic_corpus, tmp_path):
    """Stub provisioning/execution so the CLI runs without docker.

    Returns a dict capturing the RunConfig and refs the runner received.
    """
    captured: dict = {}
    credential = Credential(kind=CredentialKind.API_KEY, value="sk-secret-never-logged")

    monkeypatch.setattr(cli, "preflight_run", lambda env, model, docker: (credential, model))
    monkeypatch.setattr(cli, "check_docker", lambda docker: None)
    monkeypatch.setattr(cli, "ensure_runtime", lambda cache, docker, force=False: tmp_path / "rt")
    monkeypatch.setattr(cli, "materialize_config", lambda src, dest: dest)

    def fake_run_workflow(cfg, ref, tasks, runtime_dir, config_dir, docker, **kwargs):
        captured["cfg"] = cfg
        captured.setdefault("refs", []).append(ref)
        result = Result(ref.slug, ref.token, "alpha-task", Outcome.PASSED, cfg.model, 1.0)
        return build_run(cfg.run_id, ref.slug, ref.token, cfg.model,
                         {"task_ids": ["alpha-task"]}, [result])

    monkeypatch.setattr(cli, "run_workflow", fake_run_workflow)

    def fake_run_comparison(cfg, tasks, runtime_dir, config_dir, docker):
        captured["cfg"] = cfg
        runs = [fake_run_workflow(cfg, ref, tasks, runtime_dir, config_dir, docker)
                for ref in cfg.workflows]
        return build_comparison(cfg.run_id, cfg.model, {"task_ids": ["alpha-task"]}, runs)

    monkeypatch.setattr(cli, "run_comparison", fake_run_comparison)
    return captured


def _base_run_args(corpus: Path, jobs: Path) -> list[str]:
    """Return common run args pointing at the synthetic corpus and a temp jobs dir."""
    return ["--model", "claude-opus-4-8", "--corpus", str(corpus), "--jobs-dir", str(jobs)]


def test_run_dispatches_and_builds_config(stub_pipeline, synthetic_corpus, tmp_path):
    """`run` resolves a single task and builds a RunConfig with one workflow."""
    jobs = tmp_path / "jobs"
    argv = ["run", "--command", "/somecode", "--task", "alpha-task"] + _base_run_args(synthetic_corpus, jobs)

    assert cli.main(argv) == cli.EXIT_OK
    cfg = stub_pipeline["cfg"]
    assert [w.slug for w in cfg.workflows] == ["somecode"]
    assert cfg.selection.task_ids == ["alpha-task"]
    assert cfg.model == "claude-opus-4-8"


def test_run_id_format(stub_pipeline, synthetic_corpus, tmp_path):
    """The generated run id matches <UTC timestamp>-<short hex> (FR-024)."""
    jobs = tmp_path / "jobs"
    argv = ["run", "--command", "/somecode", "--n-tasks", "1", "--seed", "0"] + _base_run_args(synthetic_corpus, jobs)

    cli.main(argv)
    assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{6}", stub_pipeline["cfg"].run_id)


def test_run_missing_model_exits_usage(synthetic_corpus, tmp_path, capsys):
    """Missing --model is an argparse usage error (exit 2)."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--command", "/somecode", "--task", "alpha-task"])
    assert exc.value.code == cli.EXIT_USAGE


def test_run_requires_exactly_one_selection(synthetic_corpus, tmp_path):
    """Two selection flags is an argparse usage error (exit 2)."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--command", "/somecode", "--model", "m", "--task", "a", "--n-tasks", "2"])
    assert exc.value.code == cli.EXIT_USAGE


def test_run_rejects_multiple_commands(stub_pipeline, synthetic_corpus, tmp_path):
    """Two --command on `run` is a usage error (exit 2), not a silent drop of all but one."""
    jobs = tmp_path / "jobs"
    argv = (
        ["run", "--command", "none", "--command", "/specflow", "--task", "alpha-task"]
        + _base_run_args(synthetic_corpus, jobs)
    )
    assert cli.main(argv) == cli.EXIT_USAGE


def test_run_unknown_task_exits_usage(stub_pipeline, synthetic_corpus, tmp_path):
    """An unknown explicit task id maps to the usage exit code (2)."""
    jobs = tmp_path / "jobs"
    argv = ["run", "--command", "/somecode", "--task", "ghost"] + _base_run_args(synthetic_corpus, jobs)
    assert cli.main(argv) == cli.EXIT_USAGE


def test_compare_requires_two_commands(stub_pipeline, synthetic_corpus, tmp_path):
    """`compare` with fewer than two --command flags is a usage error (exit 2)."""
    jobs = tmp_path / "jobs"
    argv = ["compare", "--command", "/somecode", "--task", "alpha-task"] + _base_run_args(synthetic_corpus, jobs)
    assert cli.main(argv) == cli.EXIT_USAGE


def test_compare_shares_one_selection_and_model(stub_pipeline, synthetic_corpus, tmp_path):
    """`compare` applies one resolved selection and model to every workflow (NFR-002)."""
    jobs = tmp_path / "jobs"
    argv = [
        "compare", "--command", "/somecode", "--command", "/story-to-live",
        "--task", "alpha-task",
    ] + _base_run_args(synthetic_corpus, jobs)

    assert cli.main(argv) == cli.EXIT_OK
    cfg = stub_pipeline["cfg"]
    assert [w.slug for w in cfg.workflows] == ["somecode", "story-to-live"]
    # One shared Selection object and one model for all workflows.
    assert isinstance(cfg.selection, Selection)
    assert cfg.selection.task_ids == ["alpha-task"]
    assert cfg.model == "claude-opus-4-8"


def test_prepare_runtime_no_credential_needed(monkeypatch, tmp_path, capsys):
    """`prepare-runtime` needs docker but not a credential, and prints the cache path."""
    monkeypatch.setattr(cli, "check_docker", lambda docker: None)
    built = tmp_path / "rt"
    monkeypatch.setattr(cli, "ensure_runtime", lambda cache, docker, force=False: built)

    assert cli.main(["prepare-runtime", "--jobs-dir", str(tmp_path)]) == cli.EXIT_OK
    assert str(built) in capsys.readouterr().out


def test_run_tasks_comma_split_selects_multiple(stub_pipeline, synthetic_corpus, tmp_path):
    """`--tasks a,b` resolves multiple explicit task ids from a comma-separated list."""
    jobs = tmp_path / "jobs"
    argv = (
        ["run", "--command", "/somecode", "--tasks", "alpha-task,beta-task"]
        + _base_run_args(synthetic_corpus, jobs)
    )

    assert cli.main(argv) == cli.EXIT_OK
    selection = stub_pipeline["cfg"].selection
    assert set(selection.task_ids) == {"alpha-task", "beta-task"}


def test_wfbench_error_maps_to_exit_internal(stub_pipeline, monkeypatch, synthetic_corpus, tmp_path):
    """An unexpected WfbenchError from the runner maps to EXIT_INTERNAL (1), not EXIT_USAGE (2)."""
    jobs = tmp_path / "jobs"

    def raise_wfbench(cfg, ref, tasks, runtime_dir, config_dir, docker, **kwargs):
        raise WfbenchError("simulated unexpected harness error")

    monkeypatch.setattr(cli, "run_workflow", raise_wfbench)
    argv = (
        ["run", "--command", "/somecode", "--task", "alpha-task"]
        + _base_run_args(synthetic_corpus, jobs)
    )

    assert cli.main(argv) == cli.EXIT_INTERNAL
