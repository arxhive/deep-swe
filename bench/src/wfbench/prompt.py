"""Workflow reference parsing and per-task prompt construction (FR-005/006, R5).

A workflow is referenced by the name the owner uses locally (e.g. ``/somecode`` or
``somecode``). The prompt places the normalized slash token as the FIRST line so
Claude Code expands the slash-command, followed by a blank line and the verbatim
task instruction.
"""

import re
from dataclasses import dataclass

from .errors import WfbenchError

# Filesystem-safe slug: lowercase letters, digits, hyphen, underscore.
_SLUG_SANITIZE = re.compile(r"[^a-zA-Z0-9_-]+")


@dataclass(frozen=True)
class WorkflowRef:
    """A workflow under test, identified by its local slash/skill name."""

    raw: str
    token: str
    slug: str


def parse_workflow_ref(raw: str) -> WorkflowRef:
    """Parse a CLI workflow reference into a normalized ``WorkflowRef``.

    Strips a single leading ``/``, derives a filesystem-safe ``slug``, and sets
    ``token = "/" + slug`` (the leading prompt token).

    Raises:
        WfbenchError: when ``raw`` is empty or has no usable characters.
    """
    if raw is None or not raw.strip():
        raise WfbenchError("Workflow reference is empty; pass --command <workflow>.")

    stem = raw.strip().lstrip("/").strip()
    slug = _SLUG_SANITIZE.sub("-", stem).strip("-").lower()
    if not slug:
        raise WfbenchError(f"Workflow reference '{raw}' has no usable name characters.")

    return WorkflowRef(raw=raw, token=f"/{slug}", slug=slug)


def build_prompt(ref: WorkflowRef, instruction_text: str) -> str:
    """Build the agent prompt: slash token on line 1, blank line, then instruction.

    The token MUST remain the first token so Claude Code recognizes and expands the
    slash-command (R5). The instruction is included verbatim.
    """
    return f"{ref.token}\n\n{instruction_text}"
