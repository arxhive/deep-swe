"""Custom exception hierarchy for wfbench.

Each exception carries a clear, actionable message. The CLI maps preflight,
corpus, and selection errors to a usage exit code (2) and any unexpected
``WfbenchError`` to the internal-error exit code (1). No logic lives here.
"""


class WfbenchError(Exception):
    """Base class for all wfbench errors."""


class PreflightError(WfbenchError):
    """A precondition (credential, model, or docker) was not satisfied."""


class CorpusError(WfbenchError):
    """A task directory or its ``task.toml`` is malformed or unreadable."""


class SelectionError(WfbenchError):
    """The requested task selection references unknown ids or is invalid."""


class RuntimeBuildError(WfbenchError):
    """Building the cached linux/amd64 Claude runtime failed."""


class ConfigError(WfbenchError):
    """Materializing the owner's Claude config copy failed."""


class DockerError(WfbenchError):
    """A harness-level docker invocation failed (not an expected non-zero exit)."""


class AgentError(WfbenchError):
    """Running the workflow agent inside the container failed unexpectedly."""


class GradingError(WfbenchError):
    """The grading phase failed at the harness level (not an honest test failure)."""
