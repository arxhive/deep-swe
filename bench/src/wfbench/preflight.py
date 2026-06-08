"""Preflight validation: credential, model, and docker (FR-010/025, NFR-006, SC-005).

Three independent checks so callers compose only what they need: ``run``/``compare``
require all three (``preflight_run``), while ``prepare-runtime`` needs only docker.
All checks run BEFORE any provisioning and abort with a single actionable message.
The credential value is held in memory only and is NEVER serialized.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional, Protocol

from .config import ENV_ANTHROPIC_API_KEY, ENV_CLAUDE_CODE_OAUTH_TOKEN
from .errors import PreflightError

logger = logging.getLogger(__name__)

_NO_CREDENTIAL_MESSAGE = (
    "No Claude credential found. Recommended: use your Claude subscription by running "
    "`claude setup-token` and exporting CLAUDE_CODE_OAUTH_TOKEN (no per-token charges). "
    "Alternatively set ANTHROPIC_API_KEY, which bills per-token via the Anthropic API. "
    "Aborting before provisioning."
)
_API_KEY_BILLING_WARNING = (
    "Using ANTHROPIC_API_KEY: requests are billed per-token via the Anthropic API. To use "
    "your Claude subscription instead, run `claude setup-token`, export "
    "CLAUDE_CODE_OAUTH_TOKEN, and unset ANTHROPIC_API_KEY."
)
_PREFER_OAUTH_WARNING = (
    "Both CLAUDE_CODE_OAUTH_TOKEN and ANTHROPIC_API_KEY are set; using the subscription "
    "token and ignoring the API key. Only the token is forwarded to the sandbox, so no "
    "per-token API charges are incurred."
)
_NO_MODEL_MESSAGE = "A model is required; pass --model <model>. There is no default model."


class CredentialKind(str, Enum):
    """Which Claude credential env var supplied the value."""

    API_KEY = "api_key"
    OAUTH_TOKEN = "oauth_token"


@dataclass(frozen=True)
class Credential:
    """A validated Claude credential. ``value`` is never serialized or logged."""

    kind: CredentialKind
    value: str

    def __repr__(self) -> str:
        """Return a redacted representation so the value never appears in logs."""
        return f"Credential(kind={self.kind!r}, value=<redacted>)"

    @property
    def env_var(self) -> str:
        """Return the docker env var NAME to forward (value inherited from the host env)."""
        if self.kind is CredentialKind.API_KEY:
            return ENV_ANTHROPIC_API_KEY
        return ENV_CLAUDE_CODE_OAUTH_TOKEN


class _DockerProbe(Protocol):
    """Minimal protocol for the docker availability probe (decouples from DockerCli)."""

    def available(self) -> bool:
        """Return True if the docker daemon responds."""


def resolve_credential(env: Mapping[str, str]) -> Credential:
    """Resolve the Claude credential, preferring the subscription token (FR-025/SC-005).

    The subscription token (CLAUDE_CODE_OAUTH_TOKEN) is preferred over an API key so a
    stray ANTHROPIC_API_KEY never silently switches the run to per-token API billing;
    only the resolved credential is forwarded to the sandbox. An API-key-only run logs
    a per-token billing warning.

    Raises:
        PreflightError: when neither accepted form is present. The message recommends
            the subscription token and ``claude setup-token``.
    """
    api_key = (env.get(ENV_ANTHROPIC_API_KEY) or "").strip()
    oauth = (env.get(ENV_CLAUDE_CODE_OAUTH_TOKEN) or "").strip()

    if oauth:
        if api_key:
            logger.warning(_PREFER_OAUTH_WARNING)
        else:
            logger.info("Using Claude subscription via %s.", ENV_CLAUDE_CODE_OAUTH_TOKEN)
        return Credential(kind=CredentialKind.OAUTH_TOKEN, value=oauth)
    if api_key:
        logger.warning(_API_KEY_BILLING_WARNING)
        return Credential(kind=CredentialKind.API_KEY, value=api_key)
    raise PreflightError(_NO_CREDENTIAL_MESSAGE)


def require_model(model: Optional[str]) -> str:
    """Return ``model`` or raise ``PreflightError`` when it is missing (FR-010)."""
    if model is None or not model.strip():
        raise PreflightError(_NO_MODEL_MESSAGE)
    return model.strip()


def check_docker(docker: _DockerProbe) -> None:
    """Verify docker is available via the wrapper (NFR-006).

    Raises:
        PreflightError: when the docker daemon does not respond.
    """
    if not docker.available():
        raise PreflightError(
            "Docker is required but not available: the docker daemon did not respond."
        )
    logger.info("Docker is available.")


def preflight_run(
    env: Mapping[str, str], model: Optional[str], docker: _DockerProbe
) -> tuple[Credential, str]:
    """Compose all three checks for ``run``/``compare`` (credential, model, docker).

    Runs before any provisioning. Returns the validated credential and model.

    Raises:
        PreflightError: on the first failing check.
    """
    credential = resolve_credential(env)
    resolved_model = require_model(model)
    check_docker(docker)
    return credential, resolved_model
