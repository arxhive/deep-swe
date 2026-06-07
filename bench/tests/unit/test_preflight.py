"""Unit tests for preflight credential/model/docker validation (FR-010/025, SC-005)."""

import pytest

from wfbench.errors import PreflightError
from wfbench.preflight import (
    CredentialKind,
    check_docker,
    preflight_run,
    require_model,
    resolve_credential,
)


class _FakeDocker:
    """A docker probe stub returning a fixed availability."""

    def __init__(self, available: bool) -> None:
        self._available = available

    def available(self) -> bool:
        """Return the configured availability."""
        return self._available


def test_resolve_api_key_only() -> None:
    """ANTHROPIC_API_KEY alone resolves to an api_key credential."""
    cred = resolve_credential({"ANTHROPIC_API_KEY": "sk-test"})
    assert cred.kind is CredentialKind.API_KEY
    assert cred.env_var == "ANTHROPIC_API_KEY"
    assert cred.value == "sk-test"


def test_resolve_oauth_token_only() -> None:
    """CLAUDE_CODE_OAUTH_TOKEN alone resolves to an oauth_token credential."""
    cred = resolve_credential({"CLAUDE_CODE_OAUTH_TOKEN": "oat-test"})
    assert cred.kind is CredentialKind.OAUTH_TOKEN
    assert cred.env_var == "CLAUDE_CODE_OAUTH_TOKEN"


def test_resolve_no_credential_message_names_both_forms() -> None:
    """No credential raises a message naming both forms and claude setup-token."""
    with pytest.raises(PreflightError) as excinfo:
        resolve_credential({})

    message = str(excinfo.value)
    assert "ANTHROPIC_API_KEY" in message
    assert "CLAUDE_CODE_OAUTH_TOKEN" in message
    assert "claude setup-token" in message


def test_resolve_both_credentials_rejected() -> None:
    """Both credentials set is an error (exactly one must be present)."""
    with pytest.raises(PreflightError):
        resolve_credential({"ANTHROPIC_API_KEY": "a", "CLAUDE_CODE_OAUTH_TOKEN": "b"})


def test_resolve_blank_values_treated_as_absent() -> None:
    """Whitespace-only credential values are treated as absent."""
    with pytest.raises(PreflightError):
        resolve_credential({"ANTHROPIC_API_KEY": "   "})


def test_require_model_rejects_none_and_empty() -> None:
    """require_model rejects None and blank strings (FR-010)."""
    with pytest.raises(PreflightError):
        require_model(None)
    with pytest.raises(PreflightError):
        require_model("  ")


def test_require_model_returns_trimmed() -> None:
    """A valid model is returned trimmed."""
    assert require_model("  claude-opus-4-8 ") == "claude-opus-4-8"


def test_check_docker_raises_when_unavailable() -> None:
    """check_docker raises PreflightError when the daemon does not respond."""
    with pytest.raises(PreflightError):
        check_docker(_FakeDocker(available=False))


def test_preflight_run_composes_all_checks() -> None:
    """preflight_run returns the credential and model when all checks pass."""
    credential, model = preflight_run(
        {"ANTHROPIC_API_KEY": "sk-test"}, "claude-opus-4-8", _FakeDocker(True)
    )
    assert credential.kind is CredentialKind.API_KEY
    assert model == "claude-opus-4-8"


def test_preflight_run_fails_fast_before_docker() -> None:
    """A missing credential aborts before the docker check is reached."""
    with pytest.raises(PreflightError):
        preflight_run({}, "claude-opus-4-8", _FakeDocker(available=True))
