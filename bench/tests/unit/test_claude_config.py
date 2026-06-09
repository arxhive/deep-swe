"""Unit tests for materializing the owner's Claude config (R4, C-009)."""

import json
from pathlib import Path

import pytest

from wfbench.claude_config import materialize_config
from wfbench.errors import ConfigError


def _build_fake_config(root: Path) -> Path:
    """Create a fake ~/.claude where commands/ is a symlink and secrets exist.

    Returns the path to the fake config root to pass as the copy source.
    """
    # Real dotfiles target that the config symlinks into.
    dotfiles = root / "dotfiles"
    (dotfiles / "commands").mkdir(parents=True)
    (dotfiles / "commands" / "somecode.md").write_text("# somecode", encoding="utf-8")
    (dotfiles / "skills").mkdir()
    (dotfiles / "skills" / "worktree.md").write_text("# worktree", encoding="utf-8")

    config = root / ".claude"
    config.mkdir()
    # Symlinked entries (as on the real host).
    (config / "commands").symlink_to(dotfiles / "commands")
    (config / "skills").symlink_to(dotfiles / "skills")
    # A real settings file.
    (config / "settings.json").write_text('{"k": "v"}', encoding="utf-8")
    # Secret/large dirs that MUST be excluded.
    (config / "projects").mkdir()
    (config / "projects" / "secret.txt").write_text("SENSITIVE", encoding="utf-8")
    (config / "history.jsonl").write_text("SENSITIVE", encoding="utf-8")
    (config / "stats-cache.json").write_text("cache", encoding="utf-8")
    return config


def test_materialize_resolves_symlinks_and_copies_allowed(tmp_path: Path) -> None:
    """Symlinked commands/skills are copied as real content; settings.json copied."""
    source = _build_fake_config(tmp_path / "home")
    dest = tmp_path / "out"

    materialize_config(source, dest)

    commands = dest / "commands"
    assert commands.is_dir()
    assert not commands.is_symlink()  # resolved to real content
    assert (commands / "somecode.md").read_text(encoding="utf-8") == "# somecode"
    assert (dest / "skills" / "worktree.md").exists()
    assert (dest / "settings.json").read_text(encoding="utf-8") == '{"k": "v"}'


def test_materialize_excludes_secrets(tmp_path: Path) -> None:
    """Secret and cache entries are never copied into the destination."""
    source = _build_fake_config(tmp_path / "home")
    dest = tmp_path / "out"

    materialize_config(source, dest)

    assert not (dest / "projects").exists()
    assert not (dest / "history.jsonl").exists()
    assert not (dest / "stats-cache.json").exists()


def test_materialize_copy_is_writable(tmp_path: Path) -> None:
    """The materialized config must be writable (Claude writes state under HOME)."""
    source = _build_fake_config(tmp_path / "home")
    dest = tmp_path / "out"

    materialize_config(source, dest)

    probe = dest / "commands" / "new-file.txt"
    probe.write_text("agent state", encoding="utf-8")  # would raise if read-only
    assert probe.read_text(encoding="utf-8") == "agent state"


def test_materialize_missing_commands_raises(tmp_path: Path) -> None:
    """A source lacking commands/ raises ConfigError (the workflow cannot resolve)."""
    config = tmp_path / ".claude"
    config.mkdir()
    (config / "skills").mkdir()
    (config / "settings.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ConfigError):
        materialize_config(config, tmp_path / "out")


def test_materialize_missing_skills_raises(tmp_path: Path) -> None:
    """A source lacking skills/ raises ConfigError (the workflow cannot resolve its skills)."""
    config = tmp_path / ".claude"
    config.mkdir()
    (config / "commands").mkdir()
    # skills/ deliberately absent

    with pytest.raises(ConfigError):
        materialize_config(config, tmp_path / "out")


def test_materialize_missing_source_raises(tmp_path: Path) -> None:
    """A non-existent source config raises ConfigError."""
    with pytest.raises(ConfigError):
        materialize_config(tmp_path / "nope", tmp_path / "out")


def test_materialize_sanitizes_host_coupled_settings(tmp_path: Path) -> None:
    """Hooks/statusLine/plugins/auth-helpers are stripped; benign keys are preserved.

    These invoke host commands or override the forwarded credential, breaking a headless
    container run; benign behavior settings must survive.
    """
    config = tmp_path / ".claude"
    (config / "commands").mkdir(parents=True)
    (config / "skills").mkdir()
    settings = {
        "model": "opus",
        "permissions": {"defaultMode": "bypassPermissions"},
        "hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "host-script"}]}]},
        "statusLine": {"type": "command", "command": "npx powerline"},
        "enabledPlugins": {"pr-review-toolkit@x": True},
        "enableAllProjectMcpServers": True,
        "apiKeyHelper": "/usr/local/bin/get-key.sh",
    }
    (config / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    materialize_config(config, tmp_path / "out")

    written = json.loads((tmp_path / "out" / "settings.json").read_text(encoding="utf-8"))
    for dropped in ("hooks", "statusLine", "enabledPlugins",
                    "enableAllProjectMcpServers", "apiKeyHelper"):
        assert dropped not in written
    assert written["model"] == "opus"
    assert written["permissions"] == {"defaultMode": "bypassPermissions"}
