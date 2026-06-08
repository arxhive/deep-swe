"""Workflow reference parsing and per-task prompt construction (FR-005/006, R5).

A workflow is referenced by the name the owner uses locally (e.g. ``/somecode`` or
``somecode``). The prompt places the normalized slash token as the FIRST line so
Claude Code expands the slash-command, followed by a blank line and the verbatim
task instruction.

A reserved bare reference (``none``, ``model``, or ``baseline``, case-insensitive
and WITHOUT a leading slash) selects the pure-model baseline: no slash-command is
prepended and the model receives only the task instruction. This is the control
for measuring whether a workflow beats vanilla Claude. A real slash-command that
happens to share one of those names must be passed with its leading slash
(e.g. ``/model``).
"""

import re
from dataclasses import dataclass

from .errors import WfbenchError

# Filesystem-safe slug: lowercase letters, digits, hyphen, underscore.
_SLUG_SANITIZE = re.compile(r"[^a-zA-Z0-9_-]+")

# Reserved bare references that select the pure-model baseline (no slash-command).
_BASELINE_ALIASES = frozenset({"none", "model", "baseline"})

# Stable identity used for the baseline across artifacts, reports, and rankings.
BASELINE_SLUG = "baseline"


@dataclass(frozen=True)
class WorkflowRef:
    """A workflow under test, identified by its local slash/skill name.

    ``is_baseline`` marks the pure-model control, for which ``build_prompt`` omits
    the slash token and feeds the model the task instruction unchanged.
    """

    raw: str
    token: str
    slug: str
    is_baseline: bool = False


def parse_workflow_ref(raw: str) -> WorkflowRef:
    """Parse a CLI workflow reference into a normalized ``WorkflowRef``.

    A reserved bare word (``none``/``model``/``baseline``, no leading slash) yields
    the pure-model baseline ref. Otherwise strips a single leading ``/``, derives a
    filesystem-safe ``slug``, and sets ``token = "/" + slug`` (the leading prompt
    token).

    Raises:
        WfbenchError: when ``raw`` is empty or has no usable characters.
    """
    if raw is None or not raw.strip():
        raise WfbenchError("Workflow reference is empty; pass --command <workflow>.")

    stripped = raw.strip()
    had_slash = stripped.startswith("/")
    stem = stripped.lstrip("/").strip()

    if not had_slash and stem.lower() in _BASELINE_ALIASES:
        return WorkflowRef(raw=raw, token=BASELINE_SLUG, slug=BASELINE_SLUG, is_baseline=True)

    slug = _SLUG_SANITIZE.sub("-", stem).strip("-").lower()
    if not slug:
        raise WfbenchError(f"Workflow reference '{raw}' has no usable name characters.")

    return WorkflowRef(raw=raw, token=f"/{slug}", slug=slug)


def build_prompt(ref: WorkflowRef, instruction_text: str) -> str:
    """Build the agent prompt for a task.

    For the pure-model baseline the prompt is the task instruction verbatim (no
    slash-command). Otherwise the slash token is the first line, then a blank line,
    then the instruction, so Claude Code recognizes and expands the slash-command
    (R5). The instruction is included verbatim in both cases.
    """
    if ref.is_baseline:
        return instruction_text
    return f"{ref.token}\n\n{instruction_text}"
