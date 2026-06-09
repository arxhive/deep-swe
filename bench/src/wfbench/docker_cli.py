"""Thin subprocess wrapper over the ``docker`` CLI.

The host's interactive zsh defines a ``docker()`` function that injects
``--platform linux/amd64`` for ``run``/``build`` on arm64. ``subprocess`` execs the
real binary directly and bypasses that function, so this wrapper injects the flag
itself for ``run``/``build``/``pull`` ONLY (``exec``/``network``/``cp``/``rm`` do not
accept it) and also sets ``DOCKER_DEFAULT_PLATFORM`` in the child env as defense in
depth (R2). Methods return a result object; ``DockerError`` is raised only for
harness-level failures (the binary could not be launched), never for an expected
non-zero exit - callers decide what a non-zero exit means.
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional, Sequence

from .config import (
    DEFAULT_DOCKER_BIN,
    DOCKER_DEFAULT_PLATFORM_ENV,
    DOCKER_PLATFORM,
)
from .errors import DockerError

logger = logging.getLogger(__name__)

# Subcommands that accept and require the explicit --platform flag.
_PLATFORM_SUBCOMMANDS = frozenset({"run", "build", "pull"})


@dataclass(frozen=True)
class DockerResult:
    """The outcome of one docker invocation."""

    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        """True when the docker process exited zero."""
        return self.returncode == 0


class DockerCli:
    """Invokes the docker binary, centralizing the platform-injection nuance."""

    def __init__(self, binary: str = DEFAULT_DOCKER_BIN):
        self._binary = binary

    def _child_env(self) -> dict[str, str]:
        """Return the child env with ``DOCKER_DEFAULT_PLATFORM`` forced (defense in depth)."""
        env = dict(os.environ)
        env[DOCKER_DEFAULT_PLATFORM_ENV] = DOCKER_PLATFORM
        return env

    def _compose_args(self, subcommand: str, rest: Sequence[str]) -> list[str]:
        """Build the full argv, injecting --platform for run/build/pull only."""
        args = [self._binary, subcommand]
        if subcommand in _PLATFORM_SUBCOMMANDS:
            args += ["--platform", DOCKER_PLATFORM]
        args += list(rest)
        return args

    def _invoke(
        self, subcommand: str, rest: Sequence[str], timeout: Optional[float] = None,
        stdin_text: Optional[str] = None,
    ) -> DockerResult:
        """Run one docker subcommand and return a ``DockerResult``.

        Raises:
            DockerError: only when the docker binary cannot be launched.
        """
        args = self._compose_args(subcommand, rest)
        logger.debug("docker invoke: %s", " ".join(args))
        try:
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                input=stdin_text,
                env=self._child_env(),
                check=False,
            )
        except FileNotFoundError as exc:
            raise DockerError(f"docker binary not found: {self._binary}") from exc
        return DockerResult(
            args=args,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

    def available(self) -> bool:
        """Return True if the docker daemon responds to ``docker info``."""
        try:
            result = self._invoke("info", ["--format", "{{.ServerVersion}}"], timeout=30)
        except DockerError:
            return False
        return result.ok

    def image_exists(self, ref: str) -> bool:
        """Return True if a local image with ``ref`` is present (no pull)."""
        result = self._invoke("image", ["inspect", ref], timeout=60)
        return result.ok

    def pull(self, ref: str, timeout: Optional[float] = None) -> DockerResult:
        """Pull an image for ``linux/amd64`` (platform flag injected)."""
        return self._invoke("pull", [ref], timeout=timeout)

    def run_detached(
        self, run_args: Sequence[str], timeout: Optional[float] = None
    ) -> DockerResult:
        """Start a detached container (``docker run -d ...``); container id on stdout."""
        return self._invoke("run", run_args, timeout=timeout)

    def run_oneshot(
        self, run_args: Sequence[str], timeout: Optional[float] = None
    ) -> DockerResult:
        """Run a foreground container to completion (the one-time runtime build)."""
        return self._invoke("run", run_args, timeout=timeout)

    def build(self, build_args: Sequence[str], timeout: Optional[float] = None) -> DockerResult:
        """Run ``docker build`` for ``linux/amd64`` (platform flag injected)."""
        return self._invoke("build", build_args, timeout=timeout)

    @staticmethod
    def _exec_rest(
        container_id: str, command: Sequence[str], env: Optional[Sequence[str]],
        workdir: Optional[str], with_stdin: bool,
    ) -> list[str]:
        """Build the argv after ``docker exec``.

        ``-i`` is required when a prompt is piped on stdin: ``docker exec`` discards the
        host's stdin without it, so claude would see no input and abort. Env vars are
        forwarded by NAME only (value inherited from the child env, never in argv).
        """
        rest: list[str] = []
        if with_stdin:
            rest.append("-i")
        for name in env or []:
            rest += ["-e", name]
        if workdir is not None:
            rest += ["-w", workdir]
        rest.append(container_id)
        rest += list(command)
        return rest

    def exec(
        self, container_id: str, command: Sequence[str], timeout: Optional[float] = None,
        env: Optional[Sequence[str]] = None, workdir: Optional[str] = None,
        stdin_text: Optional[str] = None,
    ) -> DockerResult:
        """Run ``docker exec`` in a running container (NO platform flag).

        Passes ``-i`` when ``stdin_text`` is provided so the piped prompt reaches the
        container process.
        """
        rest = self._exec_rest(container_id, command, env, workdir, stdin_text is not None)
        return self._invoke("exec", rest, timeout=timeout, stdin_text=stdin_text)

    def network_disconnect(self, container_id: str, network: str) -> DockerResult:
        """Disconnect a running container from a network (NO platform flag)."""
        return self._invoke("network", ["disconnect", network, container_id], timeout=60)

    def cp(self, source: str, dest: str) -> DockerResult:
        """Copy files between host and container via the daemon (NO platform flag)."""
        return self._invoke("cp", [source, dest], timeout=300)

    def rm_force(self, container_id: str) -> DockerResult:
        """Force-remove a container (NO platform flag); used for cleanup."""
        return self._invoke("rm", ["-f", container_id], timeout=120)
