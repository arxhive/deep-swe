"""Build-once, cache, reuse the cross-architecture Claude runtime (C-007, R3).

``@anthropic-ai/claude-code`` bundles platform-specific native binaries, so it must
be installed inside ``linux/amd64`` Linux, not on the arm64 macOS host. We build it
exactly once into ``<cache>/runtime`` (an ``npm/`` global prefix plus a copied ``node``
binary) and mount that directory read-only into every task container, avoiding a
per-task reinstall across the corpus.
"""

import logging
from pathlib import Path

from .config import (
    CLAUDE_CODE_PACKAGE,
    CLAUDE_CODE_VERSION,
    NODE_IMAGE,
    RUNTIME_DIR_NAME,
)
from .docker_cli import DockerCli
from .errors import RuntimeBuildError

logger = logging.getLogger(__name__)

# Built inside the node image: install claude-code into /out/npm and copy node into /out.
_BUILD_SCRIPT = (
    "set -e; "
    f"npm install -g --prefix /out/npm {CLAUDE_CODE_PACKAGE}@{CLAUDE_CODE_VERSION}; "
    'cp -aL "$(command -v node)" /out/node'
)

# Marker that lets us treat a runtime dir as already-built without re-running docker.
_CLAUDE_BIN_RELPATH = Path("npm") / "bin" / "claude"
_NODE_BIN_RELPATH = Path("node")


def _is_built(runtime_dir: Path) -> bool:
    """Return True if a prior build left the claude and node artifacts in place."""
    has_claude = (runtime_dir / _CLAUDE_BIN_RELPATH).exists()
    has_node = (runtime_dir / _NODE_BIN_RELPATH).exists()
    return has_claude and has_node


def ensure_runtime(cache_dir: Path, docker: DockerCli, force: bool = False) -> Path:
    """Ensure the cached ``linux/amd64`` Claude runtime exists; build it once if missing.

    Args:
        cache_dir: Parent cache directory; the runtime lands in ``cache_dir/runtime``.
        docker: Docker wrapper (injects ``--platform linux/amd64``).
        force: Rebuild even if a runtime is already present.

    Returns:
        The runtime directory to mount read-only.

    Raises:
        RuntimeBuildError: when the one-time install fails (including an unavailable
            pinned version, R-RISK-2).
    """
    runtime_dir = cache_dir / RUNTIME_DIR_NAME
    if _is_built(runtime_dir) and not force:
        logger.info("Reusing cached Claude runtime at %s", runtime_dir)
        return runtime_dir

    runtime_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Building Claude runtime %s@%s into %s (one-time)",
        CLAUDE_CODE_PACKAGE, CLAUDE_CODE_VERSION, runtime_dir,
    )
    result = docker.run_oneshot(
        [
            "--rm",
            "-v", f"{runtime_dir}:/out",
            NODE_IMAGE,
            "bash", "-c", _BUILD_SCRIPT,
        ],
    )
    if not result.ok:
        raise RuntimeBuildError(
            f"Failed to build the Claude runtime ({CLAUDE_CODE_PACKAGE}@{CLAUDE_CODE_VERSION}). "
            f"docker exit {result.returncode}: {result.stderr.strip()[-500:]}"
        )
    if not _is_built(runtime_dir):
        raise RuntimeBuildError(
            f"Claude runtime build reported success but artifacts are missing under {runtime_dir}."
        )
    logger.info("Claude runtime ready at %s", runtime_dir)
    return runtime_dir
