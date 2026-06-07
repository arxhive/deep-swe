"""Unit tests for token/cost extraction from the agent result JSON (FR-019, SC-004)."""

import json

from wfbench.usage import parse_agent_usage


def _result_json(**overrides) -> str:
    """Build a representative claude -p result JSON object as a string."""
    payload = {
        "type": "result",
        "subtype": "success",
        "total_cost_usd": 0.1234,
        "usage": {
            "input_tokens": 1500,
            "output_tokens": 320,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 8000,
        },
        "result": "done",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_extracts_tokens_and_cost() -> None:
    """A representative result JSON yields the token breakdown and cost."""
    tokens, cost = parse_agent_usage(_result_json())

    assert tokens["input_tokens"] == 1500
    assert tokens["output_tokens"] == 320
    assert tokens["cache_read_input_tokens"] == 8000
    assert tokens["total"] == 1820
    assert cost == 0.1234


def test_extracts_from_multiline_stdout() -> None:
    """The result line is found even when preceded by other stdout lines."""
    text = "some streamed line\n" + _result_json() + "\n"
    tokens, cost = parse_agent_usage(text)

    assert tokens is not None
    assert cost == 0.1234


def test_missing_usage_returns_none_tokens() -> None:
    """A result without a usage block returns None tokens but may keep cost."""
    text = json.dumps({"type": "result", "total_cost_usd": 0.5})
    tokens, cost = parse_agent_usage(text)

    assert tokens is None
    assert cost == 0.5


def test_missing_cost_returns_none_cost() -> None:
    """A result without a cost field returns None cost gracefully."""
    text = json.dumps({"type": "result", "usage": {"input_tokens": 10, "output_tokens": 5}})
    tokens, cost = parse_agent_usage(text)

    assert tokens["total"] == 15
    assert cost is None


def test_empty_and_malformed_return_none() -> None:
    """Empty and non-JSON stdout return (None, None) without raising."""
    assert parse_agent_usage("") == (None, None)
    assert parse_agent_usage("not json at all") == (None, None)
    assert parse_agent_usage("{broken") == (None, None)
