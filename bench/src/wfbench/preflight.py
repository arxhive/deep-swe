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
    "No Claude credential found. Set ANTHROPIC_API_KEY, or set CLAUDE_CODE_OAUTH_TOKEN "
    "(mint one with `claude setup-token`). Aborting before provisioning."
)
_BOTH_CREDENTIALS_MESSAGE = (
    "Both ANTHROPIC_API_KEY and CLAUDE_CODE_OAUTH_TOKEN are set; exactly one must be "
    "set. Unset one and retry."
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
    """Resolve exactly one Claude credential from the environment (FR-025/SC-005).

    Raises:
        PreflightError: when neither or both accepted forms are present. The
            no-credential message names both forms and ``claude setup-token``.
    """
    api_key = (env.get(ENV_ANTHROPIC_API_KEY) or "").strip()
    oauth = (env.get(ENV_CLAUDE_CODE_OAUTH_TOKEN) or "").strip()

    if api_key and oauth:
        raise PreflightError(_BOTH_CREDENTIALS_MESSAGE)
    if api_key:
        logger.info("Using credential from %s.", ENV_ANTHROPIC_API_KEY)
        return Credential(kind=CredentialKind.API_KEY, value=api_key)
    if oauth:
        logger.info("Using credential from %s.", ENV_CLAUDE_CODE_OAUTH_TOKEN)
        return Credential(kind=CredentialKind.OAUTH_TOKEN, value=oauth)
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
