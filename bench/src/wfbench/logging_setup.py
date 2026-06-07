"""Structured logging configuration for the wfbench CLI."""

import logging
import sys

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def configure_logging(verbose: bool) -> None:
    """Configure root logging to stderr with timestamps.

    Args:
        verbose: When True, set DEBUG level; otherwise INFO. All records are
            written to stderr so stdout stays reserved for the at-a-glance
            summary (CLI contract: progress to stderr, summary to stdout).
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    # Replace any pre-existing handlers so repeated CLI invocations in one
    # process (e.g. tests) do not duplicate log lines.
    root.handlers.clear()
    root.addHandler(handler)
