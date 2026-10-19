"""Tests for goal and assist points (src/attacking_points.py)."""

import pandas as pd
import pytest

from src.attacking_points import evaluate, expected_attacking, shrunk_per_90

SCORING = {"goals_scored": {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4}, "assists": 3}


def test_shrunk_rate_with_no_minutes_is_position_average():
    assert shrunk_per_90(total=0, minutes=0, position_rate=0.3) == pytest.approx(0.3)


def test_shrunk_rate_with_lots_of_minutes_is_close_to_own_rate():
    # 0.8 per 90 over 30 matches, position average 0.3.
    assert shrunk_per_90(total=24, minutes=2700, position_rate=0.3) == pytest.approx(0.8, abs=0.05)


def test_expected_attacking_basic():
    goals, assists, points = expected_attacking(
        xg90=0.5, xa90=0.2, expected_minutes=90, opponent_factor=1.0,
        position="FWD", scoring=SCORING,
    )
    assert goals == pytest.approx(0.5)
    assert assists == pytest.approx(0.2)
    assert points == pytest.approx(0.5 * 4 + 0.2 * 3)


def test_easier_opponent_scales_up():
    # Opponent concedes twice as much as average: everything doubles.
    goals, assists, _ = expected_attacking(0.5, 0.2, 90, opponent_factor=2.0,
                                           position="MID", scoring=SCORING)
    assert goals == pytest.approx(1.0)
    assert assists == pytest.approx(0.4)


def test_half_a_match_halves_it():
    full = expected_attacking(0.5, 0.2, 90, 1.0, "MID", SCORING)[2]
    half = expected_attacking(0.5, 0.2, 45, 1.0, "MID", SCORING)[2]
    assert half == pytest.approx(full / 2)


def test_goal_values_differ_by_position():
    defender = expected_attacking(0.1, 0.0, 90, 1.0, "DEF", SCORING)[2]
    forward = expected_attacking(0.1, 0.0, 90, 1.0, "FWD", SCORING)[2]
    assert defender == pytest.approx(0.6)
    assert forward == pytest.approx(0.4)


def _history(rows):
    return pd.DataFrame(rows, columns=[
        "element", "position", "team", "fixture", "gameweek", "minutes",
        "expected_goals", "expected_assists", "goals_scored", "assists", "opponent_factor",
    ])


def test_evaluate_never_uses_the_gameweek_being_predicted():
    def season(gw3_goals, gw3_xg):
        rows = [(1, "FWD", "A", gw, gw, 90, 0.6, 0.1, 1, 0, 1.0) for gw in (1, 2)]
        rows += [(2, "MID", "A", gw, gw, 90, 0.2, 0.3, 0, 1, 1.0) for gw in (1, 2)]
        rows += [(1, "FWD", "A", 3, 3, 90, gw3_xg, 0.1, gw3_goals, 0, 1.2),
                 (2, "MID", "A", 3, 3, 90, 0.2, 0.3, 0, 0, 1.2)]
        return _history(rows)

    normal = evaluate(season(1, 0.6), gameweeks=[3], scoring=SCORING)
    changed = evaluate(season(4, 3.0), gameweeks=[3], scoring=SCORING)
    for column in ("predicted", "predicted_no_fixture", "recent_average"):
        pd.testing.assert_series_equal(normal[column], changed[column])
    assert changed["actual"].tolist() == [16, 0]  # 4 goals x 4 points
