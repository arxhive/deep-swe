"""Deterministic task-subset selection (FR-002/003/004, NFR-001, SC-002).

Three modes: a single explicit id, an explicit id list, or a seeded ``(n, seed)``
sample. The sample sorts ids lexicographically first so the same ``(n, seed)`` yields
identical ids on every machine, independent of filesystem enumeration order.
"""

import logging
import random
from dataclasses import dataclass
from typing import Optional, Sequence

from .errors import SelectionError

logger = logging.getLogger(__name__)

MODE_EXPLICIT = "explicit"
MODE_SAMPLED = "sampled"


@dataclass(frozen=True)
class Selection:
    """A resolved, ordered set of task ids plus how it was produced."""

    task_ids: list[str]
    mode: str
    n: Optional[int] = None
    seed: Optional[int] = None


def _check_known(requested: Sequence[str], available: Sequence[str]) -> None:
    """Raise ``SelectionError`` listing any requested ids absent from ``available``."""
    available_set = set(available)
    unknown = [task_id for task_id in requested if task_id not in available_set]
    if unknown:
        raise SelectionError(
            f"Unknown task id(s): {', '.join(unknown)}. "
            "They are not present in the corpus; refusing to run."
        )


def resolve_explicit(requested: Sequence[str], available_ids: Sequence[str]) -> Selection:
    """Resolve an explicit id or id list, preserving the requested order.

    Raises:
        SelectionError: when any requested id is not in the corpus (FR-027) or the
            request is empty.
    """
    cleaned = [task_id.strip() for task_id in requested if task_id.strip()]
    if not cleaned:
        raise SelectionError("No task ids provided for explicit selection.")
    _check_known(cleaned, available_ids)
    return Selection(task_ids=list(cleaned), mode=MODE_EXPLICIT)


def resolve_sample(n: int, seed: int, available_ids: Sequence[str]) -> Selection:
    """Resolve a deterministic ``(n, seed)`` sample over sorted ids (R9).

    ``n`` larger than the corpus is capped to the corpus size and logged. ``n`` must
    be positive.

    Raises:
        SelectionError: when ``n`` is not positive or the corpus is empty.
    """
    if n <= 0:
        raise SelectionError(f"--n-tasks must be a positive integer, got {n}.")
    if not available_ids:
        raise SelectionError("Corpus contains no tasks to sample.")

    sorted_ids = sorted(available_ids)
    capped = min(n, len(sorted_ids))
    if capped < n:
        logger.warning(
            "Requested n=%d exceeds corpus size %d; capping to %d.", n, len(sorted_ids), capped
        )
    chosen = random.Random(seed).sample(sorted_ids, capped)
    return Selection(task_ids=chosen, mode=MODE_SAMPLED, n=n, seed=seed)
