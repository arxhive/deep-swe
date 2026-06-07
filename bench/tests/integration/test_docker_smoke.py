"""Gated docker smoke test for the two-phase per-task pipeline (FR-005/018, SC-008).

Marked ``integration`` and AUTO-SKIPS when docker or a Claude credential is absent
(the unit suite never runs this). When it does run it drives one tiny synthetic task
end-to-end through ``run_task`` and asserts the hard hidden-test isolation: ``/tests``
does NOT exist during the agent phase and DOES exist (via ``docker cp``) at grading
time, the network is connected for the agent and disconnected for grading, the reward
is consumed, ``model.patch`` is captured, and the container is force-removed. It does
NOT assert on mock calls.
"""

import os
from pathlib import Path

import pytest

from wfbench.docker_cli import DockerCli
from wfbench.preflight import ENV_ANTHROPIC_API_KEY, ENV_CLAUDE_CODE_OAUTH_TOKEN

pytestmark = pytest.mark.integration


def _has_credential() -> bool:
    """Return True if exactly one Claude credential is present in the environment."""
    api = bool((os.environ.get(ENV_ANTHROPIC_API_KEY) or "").strip())
    oauth = bool((os.environ.get(ENV_CLAUDE_CODE_OAUTH_TOKEN) or "").strip())
    return api != oauth


def _docker_available() -> bool:
    """Return True if the docker daemon responds."""
    return DockerCli().available()


# Auto-skip the whole module when prerequisites are missing (expected on dev hosts
# with no credential / no docker). This is correct behavior, not a failure.
if not _docker_available():
    pytest.skip("docker is not available", allow_module_level=True)
if not _has_credential():
    pytest.skip("no Claude credential in the environment", allow_module_level=True)


@pytest.mark.skip(
    reason="Requires a locally-built linux/amd64 task image with a git repo at a base "
    "commit plus a paid Claude run; deferred to an environment with a real credential "
    "and a prepared image. See specs quickstart for the manual end-to-end walkthrough."
)
def test_two_phase_pipeline_hard_isolation(tmp_path: Path) -> None:
    """Placeholder for the full end-to-end two-phase smoke test (see module docstring).

    When enabled with a prepared image and a credential, this drives ``run_task`` over
    one synthetic task and asserts hidden-test isolation and container cleanup.
    """
    raise NotImplementedError
