"""Unit tests for runner outcome-decision helpers."""

from wfbench.agent_runner import AgentOutcome
from wfbench.runner import _agent_failed


def _agent(exit_code, timed_out=False) -> AgentOutcome:
    """Build an AgentOutcome with the fields the decision depends on."""
    return AgentOutcome(
        container_id="c", exit_code=exit_code, duration_sec=1.0,
        timed_out=timed_out, stdout="", stderr="",
    )


def test_agent_failed_on_timeout() -> None:
    """A timeout is always an agent failure, regardless of patch state."""
    assert _agent_failed(_agent(None, timed_out=True), patch_present=False) is True
    assert _agent_failed(_agent(None, timed_out=True), patch_present=True) is True


def test_agent_failed_on_crash_with_no_patch() -> None:
    """A non-zero exit with no patch is a crash -> errored (e.g. claude refusing root)."""
    assert _agent_failed(_agent(1), patch_present=False) is True


def test_agent_not_failed_when_nonzero_exit_but_patch_present() -> None:
    """A non-zero exit that still left a change defers to the reward (it may pass)."""
    assert _agent_failed(_agent(1), patch_present=True) is False


def test_agent_not_failed_on_clean_exit() -> None:
    """A clean zero exit is not an agent failure."""
    assert _agent_failed(_agent(0), patch_present=False) is False
