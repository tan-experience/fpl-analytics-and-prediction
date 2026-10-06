"""Tests for the points projection formula (src/models.py)."""

import pandas as pd

from src.models import (
    FIXTURE_DIFFICULTY_WEIGHT,
    _fixture_adjustment,
    _playing_probability,
    project_gameweek_points,
)


def test_fixture_adjustment_direction():
    assert _fixture_adjustment(1) > 0  # easy fixture -> boost
    assert _fixture_adjustment(3) == 0  # average fixture -> no change
    assert _fixture_adjustment(5) < 0  # hard fixture -> penalty
    assert _fixture_adjustment(None) == 0  # no fixture found -> no change


def test_playing_probability():
    assert _playing_probability(None) == 1.0  # no injury doubt
    assert _playing_probability(75) == 0.75
    assert _playing_probability(0) == 0.0


def _features(**overrides) -> pd.DataFrame:
    row = {"form": 5.0, "next_fixture_difficulty": 2,
           "chance_of_playing_next_round": None, "status": "a"}
    row.update(overrides)
    return pd.DataFrame([row])


def test_projection_formula():
    projected = project_gameweek_points(_features()).loc[0, "projected_points"]
    assert projected == 5.0 + 1 * FIXTURE_DIFFICULTY_WEIGHT


def test_projection_discounted_by_injury_doubt():
    projected = project_gameweek_points(_features(chance_of_playing_next_round=50))
    assert projected.loc[0, "projected_points"] == 0.5 * (5.0 + FIXTURE_DIFFICULTY_WEIGHT)


def test_projection_never_negative():
    # No form + a hard fixture used to give -0.15 (shown as "-0.0" on the
    # bench). A hard fixture alone shouldn't predict LOSING points.
    projected = project_gameweek_points(_features(form=0.0, next_fixture_difficulty=5))
    assert projected.loc[0, "projected_points"] == 0.0


def test_unavailable_player_projects_zero():
    # Status 'i' = injured: stale form must not produce a projection.
    projected = project_gameweek_points(_features(status="i"))
    assert projected.loc[0, "projected_points"] == 0.0
