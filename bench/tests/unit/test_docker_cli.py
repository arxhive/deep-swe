"""Unit tests for the docker exec argv builder.

Guards the stdin fix: `docker exec` drops the host's stdin unless `-i` is passed, so
the piped prompt never reaches claude and it aborts with "Input must be provided".
"""

from wfbench.docker_cli import DockerCli


def test_exec_rest_adds_dash_i_when_stdin_present() -> None:
    """`-i` must be present (before the container id) when a prompt is piped in."""
    rest = DockerCli._exec_rest("cid", ["claude", "-p"], ["TOKEN"], "/app", with_stdin=True)
    assert "-i" in rest
    assert rest.index("-i") < rest.index("cid")


def test_exec_rest_omits_dash_i_without_stdin() -> None:
    """No `-i` for non-stdin execs (mkdir, the verifier)."""
    rest = DockerCli._exec_rest("cid", ["bash", "/tests/test.sh"], None, None, with_stdin=False)
    assert "-i" not in rest


def test_exec_rest_forwards_env_by_name_and_workdir() -> None:
    """Env is forwarded by name (no value in argv) and the workdir is set."""
    rest = DockerCli._exec_rest("cid", ["x"], ["ANTHROPIC_API_KEY"], "/app", with_stdin=True)
    assert rest[rest.index("-e") + 1] == "ANTHROPIC_API_KEY"
    assert "ANTHROPIC_API_KEY=" not in " ".join(rest)  # name only, never the value
    assert rest[rest.index("-w") + 1] == "/app"
    assert rest[-2:] == ["cid", "x"]  # container id then the command, last
