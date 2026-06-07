"""Unit tests for deterministic task-subset selection (SC-002, FR-027)."""

import pytest

from wfbench.errors import SelectionError
from wfbench.selection import MODE_EXPLICIT, MODE_SAMPLED, resolve_explicit, resolve_sample

# A stable candidate pool larger than typical sample sizes; deliberately unsorted.
_IDS = ["task-c", "task-a", "task-e", "task-b", "task-d", "task-f", "task-g"]


def test_same_seed_yields_identical_ids() -> None:
    """The same (n, seed) yields byte-identical ids across calls (SC-002)."""
    first = resolve_sample(3, 7, _IDS)
    second = resolve_sample(3, 7, _IDS)

    assert first.task_ids == second.task_ids
    assert first.mode == MODE_SAMPLED
    assert first.n == 3
    assert first.seed == 7


def test_selection_is_independent_of_input_order() -> None:
    """Sorting before sampling makes the result independent of input ordering."""
    shuffled = list(reversed(_IDS))
    assert resolve_sample(4, 1, _IDS).task_ids == resolve_sample(4, 1, shuffled).task_ids


def test_different_seeds_differ() -> None:
    """Different seeds select different subsets over a large enough pool."""
    assert resolve_sample(3, 1, _IDS).task_ids != resolve_sample(3, 2, _IDS).task_ids


def test_n_greater_than_corpus_caps() -> None:
    """Requesting more than the corpus size caps to the corpus size."""
    selection = resolve_sample(100, 0, _IDS)

    assert len(selection.task_ids) == len(_IDS)
    assert sorted(selection.task_ids) == sorted(_IDS)


def test_non_positive_n_raises() -> None:
    """A non-positive sample size is a SelectionError."""
    with pytest.raises(SelectionError):
        resolve_sample(0, 0, _IDS)


def test_explicit_list_preserved_in_order() -> None:
    """An explicit id list is preserved in the requested order."""
    selection = resolve_explicit(["task-d", "task-a"], _IDS)

    assert selection.task_ids == ["task-d", "task-a"]
    assert selection.mode == MODE_EXPLICIT


def test_explicit_unknown_id_raises_listing_id() -> None:
    """An explicit unknown id raises SelectionError listing the unknown id (FR-027)."""
    with pytest.raises(SelectionError) as excinfo:
        resolve_explicit(["task-a", "ghost"], _IDS)

    assert "ghost" in str(excinfo.value)


def test_explicit_empty_raises() -> None:
    """An empty explicit selection is a SelectionError."""
    with pytest.raises(SelectionError):
        resolve_explicit([], _IDS)
