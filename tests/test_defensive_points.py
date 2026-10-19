"""Tests for clean-sheet and goals-conceded points (src/defensive_points.py)."""

import math

import pandas as pd
import pytest

from src.defensive_points import (
    clean_sheet_probability,
    expected_conceded_penalty,
    expected_defensive_points,
    play_probability,
    score_clean_sheet_predictions,
)

# Same shape as FPL's own scoring settings (bootstrap game_config).
SCORING = {
    "clean_sheets": {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0},
    "goals_conceded": {"GKP": -1, "DEF": -1, "MID": 0, "FWD": 0},
}


def test_clean_sheet_probability():
    assert clean_sheet_probability(0.0) == 1.0  # opponent expected to score nothing
    assert clean_sheet_probability(1.0) == pytest.approx(math.exp(-1))  # ~37%


def test_conceded_penalty_matches_brute_force():
    # Expected number of "every 2 goals conceded" deductions, checked by
    # adding up every possible scoreline the long way.
    lam = 1.5
    brute = sum((k // 2) * math.exp(-lam) * lam ** k / math.factorial(k) for k in range(60))
    assert expected_conceded_penalty(lam) == pytest.approx(brute)
    assert expected_conceded_penalty(0.0) == 0.0


def test_defender_points():
    pts = expected_defensive_points("DEF", opponent_expected_goals=1.0, p60=1.0, scoring=SCORING)
    assert pts == pytest.approx(4 * math.exp(-1) - expected_conceded_penalty(1.0))


def test_midfielder_gets_one_point_per_clean_sheet_and_no_penalty():
    pts = expected_defensive_points("MID", opponent_expected_goals=1.0, p60=1.0, scoring=SCORING)
    assert pts == pytest.approx(math.exp(-1))


def test_forward_gets_nothing():
    assert expected_defensive_points("FWD", 0.2, 1.0, SCORING) == 0


def test_points_scale_with_chance_of_playing_60():
    full = expected_defensive_points("DEF", 1.0, p60=1.0, scoring=SCORING)
    half = expected_defensive_points("DEF", 1.0, p60=0.5, scoring=SCORING)
    assert half == pytest.approx(full / 2)


def test_play_probability():
    assert play_probability(starts=3, team_matches=6, status="a", chance_of_playing=None) == 0.5
    assert play_probability(6, 6, "d", chance_of_playing=50) == 0.5  # 50% injury doubt
    assert play_probability(6, 6, "i", chance_of_playing=0) == 0.0  # injured
    assert play_probability(0, 0, "a", None) == 0.0  # no matches yet: no evidence they start


def test_score_clean_sheet_predictions():
    # Two perfect predictions (100% -> kept, 0% -> conceded) score a Brier of 0.
    rows = pd.DataFrame({"predicted": [0.0, 9.0], "actual": [0, 3]})  # opponent's goals
    result = score_clean_sheet_predictions(rows)
    assert result["brier"] == pytest.approx(math.exp(-9) ** 2 / 2)  # average over 2 rows, ~0
    assert result["clean_sheets"] == 1
