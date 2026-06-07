"""Parse token usage and cost from the ``claude -p --output-format json`` result (FR-019).

The Claude Code headless run emits a JSON result object on stdout carrying a
``usage`` block (input/output/cache token counts) and ``total_cost_usd``. This parser
is pure and tolerant: any missing, extra, or malformed field yields ``None`` rather
than raising, so a benchmark attempt is never aborted by an unexpected agent payload.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _extract_result_object(agent_json_text: str) -> Optional[dict]:
    """Return the result dict from the agent stdout, tolerating extra non-JSON lines.

    Tries a whole-text parse first; if the CLI emitted multiple lines, scans lines
    bottom-up for the last parseable JSON object (the final result line).
    """
    text = (agent_json_text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    return None


def _normalize_tokens(usage: dict) -> Optional[dict]:
    """Pull known integer token fields from a ``usage`` dict into a flat summary."""
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )
    tokens = {key: usage[key] for key in fields if isinstance(usage.get(key), int)}
    if not tokens:
        return None
    total = tokens.get("input_tokens", 0) + tokens.get("output_tokens", 0)
    if total:
        tokens["total"] = total
    return tokens


def parse_agent_usage(agent_json_text: str) -> tuple[Optional[dict], Optional[float]]:
    """Extract ``(tokens, cost_usd)`` from the agent result JSON; ``None`` when absent.

    Never raises on malformed or partial input; returns ``(None, None)`` in that case.
    """
    result = _extract_result_object(agent_json_text)
    if result is None:
        logger.debug("Agent stdout has no parseable JSON result object.")
        return None, None

    usage = result.get("usage")
    tokens = _normalize_tokens(usage) if isinstance(usage, dict) else None

    cost = result.get("total_cost_usd")
    cost_usd = float(cost) if isinstance(cost, (int, float)) else None

    return tokens, cost_usd
