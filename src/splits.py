"""
Chip lists (official split, leave-one-event-out) and the leakage guard.

Rule from the brief: hyperparameters are tuned on one set of chips and scored on a different
set, and no chip may be in both. `assert_disjoint` is the single place that rule is enforced.
"""

import csv
from pathlib import Path

from src.io import data_dir

OFFICIAL_FILES = {
    "train": "flood_train_data.csv",
    "valid": "flood_valid_data.csv",
    "test": "flood_test_data.csv",
    "bolivia": "flood_bolivia_data.csv",
}


def chip_event(chip_id):
    """'Sri-Lanka_233609' -> 'Sri-Lanka'. Chip ids are EVENT_NUMBER."""
    return chip_id.rsplit("_", 1)[0]


def load_official_splits(ddir=None):
    """{'train': [...], 'valid': [...], 'test': [...], 'bolivia': [...]} of chip ids."""
    ddir = Path(ddir) if ddir else data_dir()
    splits = {}
    for name, fname in OFFICIAL_FILES.items():
        with open(ddir / "splits" / fname) as f:
            splits[name] = [row[0].removesuffix("_S1Hand.tif") for row in csv.reader(f)]
    return splits


def loeo_folds(chip_ids):
    """
    Leave-one-event-out folds. Yields (held_out_event, tuning_ids, eval_ids): the evaluation set
    is every chip of the held-out event, the tuning set is every chip of all other events.
    """
    events = sorted({chip_event(c) for c in chip_ids})
    for event in events:
        eval_ids = [c for c in chip_ids if chip_event(c) == event]
        tuning_ids = [c for c in chip_ids if chip_event(c) != event]
        yield event, tuning_ids, eval_ids


def assert_disjoint(tuning_ids, eval_ids, what=""):
    """Raise if any chip id is in both sets (test-set leakage)."""
    overlap = set(tuning_ids) & set(eval_ids)
    if overlap:
        raise AssertionError(
            f"LEAKAGE {what}: {len(overlap)} chip(s) in both tuning and evaluation sets, "
            f"e.g. {sorted(overlap)[:3]}"
        )


def assert_only_from(chip_ids, allowed_ids, forbidden_ids, what=""):
    """Raise if a script that should touch only `allowed_ids` was handed anything else."""
    chip_ids = set(chip_ids)
    bad = chip_ids & set(forbidden_ids)
    if bad:
        raise AssertionError(f"{what}: forbidden chip(s) requested, e.g. {sorted(bad)[:3]}")
    stray = chip_ids - set(allowed_ids)
    if stray:
        raise AssertionError(f"{what}: chip(s) outside the allowed split, e.g. {sorted(stray)[:3]}")
