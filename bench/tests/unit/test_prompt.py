"""Unit tests for workflow-ref parsing and prompt construction (R5)."""

import pytest

from wfbench.errors import WfbenchError
from wfbench.prompt import build_prompt, parse_workflow_ref


def test_parse_normalizes_leading_slash() -> None:
    """A leading slash is stripped to derive the slug; the token re-adds it."""
    ref = parse_workflow_ref("/somecode")
    assert ref.slug == "somecode"
    assert ref.token == "/somecode"


def test_parse_without_leading_slash() -> None:
    """A bare name produces the same normalized ref as the slashed form."""
    assert parse_workflow_ref("somecode").token == "/somecode"


def test_parse_slug_is_filesystem_safe() -> None:
    """Unsafe characters in a reference collapse to a hyphenated, lowercase slug."""
    ref = parse_workflow_ref("/Story To Live!")
    assert ref.slug == "story-to-live"
    assert "/" not in ref.slug
    assert " " not in ref.slug


def test_parse_empty_raises() -> None:
    """An empty or slash-only reference raises WfbenchError."""
    with pytest.raises(WfbenchError):
        parse_workflow_ref("   ")
    with pytest.raises(WfbenchError):
        parse_workflow_ref("/")


def test_build_prompt_token_first_then_instruction() -> None:
    """The slash token is the first line, then a blank line, then the instruction."""
    ref = parse_workflow_ref("/somecode")
    instruction = "Do the thing.\nWith `backticks` and \"quotes\"."
    prompt = build_prompt(ref, instruction)

    lines = prompt.split("\n")
    assert lines[0] == "/somecode"
    assert lines[1] == ""
    assert prompt.endswith(instruction)
