"""Unit tests for the in-container agent command builder.

These guard the root-permission fix: Claude refuses bypassPermissions as root (the
task containers run as root) unless IS_SANDBOX=1 is set, so a missing flag would make
every real run fail in ~1s with an empty patch.
"""

from wfbench.agent_runner import _build_agent_command


def test_agent_command_sets_is_sandbox() -> None:
    """IS_SANDBOX=1 must be present so claude allows bypassPermissions as root."""
    assert "IS_SANDBOX=1" in _build_agent_command("opus")


def test_agent_command_runs_claude_headless_with_model() -> None:
    """The command runs `claude -p` headlessly with bypassPermissions, HOME, and the model."""
    cmd = _build_agent_command("claude-opus-4-8")

    assert cmd[0] == "env"
    assert "HOME=/root" in cmd
    assert "claude" in cmd and "-p" in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "bypassPermissions"
    assert cmd[cmd.index("--model") + 1] == "claude-opus-4-8"


def test_agent_command_has_no_credential_value() -> None:
    """The credential is forwarded separately by name; no secret appears in the argv."""
    cmd = _build_agent_command("opus")
    joined = " ".join(cmd)
    assert "ANTHROPIC_API_KEY=" not in joined
    assert "CLAUDE_CODE_OAUTH_TOKEN=" not in joined
