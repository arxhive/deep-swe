"""Security tests: the credential value never reaches argv, artifacts, or serializers (T045)."""

from pathlib import Path

from wfbench.agent_runner import _build_run_args
from wfbench.corpus import parse_task
from wfbench.preflight import Credential, CredentialKind
from wfbench.results import Outcome, Result, build_comparison, build_run

_SECRET = "sk-ant-SUPER-SECRET-VALUE-do-not-log"


def test_credential_value_absent_from_docker_argv(synthetic_corpus: Path) -> None:
    """The docker run argv carries only the env var NAME, never the secret value."""
    task = parse_task(synthetic_corpus / "alpha-task")
    cred = Credential(kind=CredentialKind.API_KEY, value=_SECRET)

    argv = _build_run_args(task, cred, Path("/rt"), Path("/cfg"))

    assert _SECRET not in " ".join(argv)
    assert "ANTHROPIC_API_KEY" in argv  # the name is forwarded
    assert "-e" in argv


def test_credential_value_absent_from_oauth_argv(synthetic_corpus: Path) -> None:
    """The same name-only forwarding holds for the oauth token credential."""
    task = parse_task(synthetic_corpus / "alpha-task")
    cred = Credential(kind=CredentialKind.OAUTH_TOKEN, value=_SECRET)

    argv = _build_run_args(task, cred, Path("/rt"), Path("/cfg"))

    assert _SECRET not in " ".join(argv)
    assert "CLAUDE_CODE_OAUTH_TOKEN" in argv


def test_result_serializer_excludes_any_credential_value() -> None:
    """Result.to_dict never carries a credential value (no field holds it)."""
    result = Result("wf", "/wf", "t1", Outcome.PASSED, "m", 1.0, reason=_SECRET[:4])
    data = result.to_dict()
    assert _SECRET not in str(data)


def test_run_and_comparison_serializers_have_no_credential() -> None:
    """Run and Comparison serializers never expose a credential field or value."""
    selection = {"task_ids": ["t1"]}
    result = Result("wf", "/wf", "t1", Outcome.PASSED, "m", 1.0)
    run = build_run("r", "wf", "/wf", "m", selection, [result])
    comparison = build_comparison("r", "m", selection, [run])

    assert _SECRET not in str(run.to_dict())
    assert _SECRET not in str(comparison.to_dict())
    assert "credential" not in run.to_dict()
    assert "credential" not in comparison.to_dict()
