"""
Leakage guard: no chip may be in both the tuning set and the evaluation set.
Covers the official split and every leave-one-event-out fold.
"""

import pytest

from src.io import data_dir
from src.splits import (assert_disjoint, assert_only_from, chip_event, load_official_splits,
                        loeo_folds)

needs_data = pytest.mark.skipif(not (data_dir() / "splits").exists(), reason="data not downloaded")


def test_guard_raises_on_overlap():
    with pytest.raises(AssertionError, match="LEAKAGE"):
        assert_disjoint(["a", "b", "c"], ["c", "d"], "unit test")


def test_guard_passes_when_disjoint():
    assert_disjoint(["a", "b"], ["c", "d"])


def test_assert_only_from_blocks_forbidden_and_stray_chips():
    assert_only_from(["v1"], allowed_ids=["v1", "v2"], forbidden_ids=["t1"])
    with pytest.raises(AssertionError):
        assert_only_from(["v1", "t1"], ["v1", "t1"], ["t1"])  # forbidden
    with pytest.raises(AssertionError):
        assert_only_from(["x"], ["v1"], ["t1"])  # not in the allowed split


def test_chip_event_parsing():
    assert chip_event("Sri-Lanka_233609") == "Sri-Lanka"
    assert chip_event("Ghana_5079") == "Ghana"


@needs_data
def test_official_splits_are_pairwise_disjoint_and_complete():
    s = load_official_splits()
    names = list(s)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert_disjoint(s[a], s[b], f"{a} vs {b}")
    assert sum(len(v) for v in s.values()) == 446
    assert_disjoint(s["valid"], s["test"], "tuning (valid) vs test")  # the protocol's own pairing


@needs_data
def test_loeo_folds_never_leak_and_cover_every_chip_once():
    s = load_official_splits()
    all_ids = [c for v in s.values() for c in v]
    folds = list(loeo_folds(all_ids))
    assert len(folds) == 11
    evaluated = []
    for event, tuning, evaluation in folds:
        assert_disjoint(tuning, evaluation, f"LOEO fold {event}")
        assert all(chip_event(c) == event for c in evaluation)
        assert all(chip_event(c) != event for c in tuning)  # held-out event never in tuning
        assert len(tuning) + len(evaluation) == 446
        evaluated += evaluation
    assert sorted(evaluated) == sorted(all_ids)  # each chip is held out exactly once
