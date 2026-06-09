"""Materialize a writable, symlink-resolved copy of the owner's ``~/.claude`` (R4, C-009).

On the host, ``commands/``, ``skills/``, ``scripts/``, and ``CLAUDE.md`` are symlinks
into the owner's dotfiles; they resolve on the host but would dangle inside a
container, so contents are copied with symlink resolution. The copy must be WRITABLE
because Claude Code writes session state under HOME ``.claude`` during a ``-p`` run.
Secret and large/host-specific directories are excluded. No credential is ever copied;
auth is provided via env.
"""

import json
import logging
import shutil
from pathlib import Path

from .config import (
    CONFIG_EXCLUDE,
    CONFIG_INCLUDE,
    CONFIG_REQUIRED,
    SETTINGS_NAME,
    SETTINGS_SANDBOX_DROP_KEYS,
)
from .errors import ConfigError

logger = logging.getLogger(__name__)

_EXCLUDE_SET = frozenset(CONFIG_EXCLUDE)


def _ignore_excluded(_dir: str, names: list[str]) -> set[str]:
    """``copytree`` ignore callback: skip excluded names and any cache-like entries."""
    return {
        name for name in names
        if name in _EXCLUDE_SET or "cache" in name.lower() or name.endswith(".jsonl")
    }


def _copy_entry(src_entry: Path, dest_entry: Path) -> None:
    """Copy one include entry (dir or file) with symlinks resolved into ``dest_entry``."""
    real = src_entry.resolve()
    if real.is_dir():
        # symlinks=False -> follow links so dotfile symlinks are materialized as content.
        shutil.copytree(real, dest_entry, symlinks=False, ignore=_ignore_excluded)
    else:
        shutil.copy2(real, dest_entry)


def _sanitize_settings(dest: Path) -> None:
    """Strip host-coupled keys from the sandbox ``settings.json`` (defense + reliability).

    Drops hooks/statusLine/plugins/project-MCP (host commands or host-only state that
    break a headless container run) and apiKeyHelper/proxyAuthHelper/awsAuthRefresh (so
    they cannot override the forwarded subscription credential). A missing, non-object,
    or unparseable settings file is left as-is with a warning (non-fatal).
    """
    settings_path = dest / SETTINGS_NAME
    if not settings_path.is_file():
        return
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not parse %s to sanitize; leaving as-is: %s", settings_path, exc)
        return
    if not isinstance(data, dict):
        logger.warning("Sandbox %s is not a JSON object; leaving as-is.", SETTINGS_NAME)
        return

    removed = [key for key in SETTINGS_SANDBOX_DROP_KEYS if key in data]
    if not removed:
        return
    for key in removed:
        data.pop(key, None)
    settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Sanitized sandbox %s (removed: %s).", SETTINGS_NAME, ", ".join(removed))


def _verify_required(dest: Path) -> None:
    """Raise ``ConfigError`` if a required entry (commands/skills) is missing in ``dest``."""
    for required in CONFIG_REQUIRED:
        if not (dest / required).exists():
            raise ConfigError(
                f"Required Claude config entry '{required}' is missing; the workflow cannot "
                f"resolve its slash-commands/skills. Looked under the resolved source config."
            )


def materialize_config(src: Path, dest: Path) -> Path:
    """Copy the allowed, resolved, writable subset of ``src`` (~/.claude) into ``dest``.

    Args:
        src: The owner's Claude config root (may contain symlinks into dotfiles).
        dest: Target directory for the per-run writable copy.

    Returns:
        The populated ``dest`` directory.

    Raises:
        ConfigError: when ``src`` is absent, or ``commands``/``skills`` cannot be found.
    """
    src = src.expanduser()
    if not src.is_dir():
        raise ConfigError(f"Claude config source does not exist: {src}")

    dest.mkdir(parents=True, exist_ok=True)
    for name in CONFIG_INCLUDE:
        src_entry = src / name
        if not src_entry.exists():
            logger.debug("Config entry not present, skipping: %s", name)
            continue
        _copy_entry(src_entry, dest / name)
        logger.debug("Copied config entry: %s", name)

    _sanitize_settings(dest)
    _verify_required(dest)
    logger.info("Materialized Claude config into %s", dest)
    return dest
