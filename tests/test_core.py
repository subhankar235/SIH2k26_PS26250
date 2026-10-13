"""Smoke tests for shared baseline behavior."""

from data.generate_synthetic_data import generate
from ml.models.forecast import moving_average
from optimisation.dispatch import meets_reserve_target


def test_synthetic_data_is_reproducible() -> None:
    assert generate(3, 4) == generate(3, 4)


def test_moving_average_and_reserve_margin() -> None:
    assert moving_average([1.0, 2.0, 3.0], 2) == 2.5
    assert meets_reserve_target(120.0, 100.0, 0.2)
