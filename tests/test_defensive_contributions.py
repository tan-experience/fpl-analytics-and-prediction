"""Tests for defensive contribution points (src/defensive_contributions.py)."""

import math

import pandas as pd
import pytest

from src.defensive_contributions import (
    THRESHOLDS,
    evaluate,
    hit_probability,
    poisson_at_least,
)


def test_thresholds_match_fpl_rules():
    # Verified against FPL's own points breakdown for GW6 (see module docs).
    assert THRESHOLDS == {"DEF": 10, "MID": 12, "FWD": 12}


def test_poisson_at_least():
    assert poisson_at_least(0.0, 10) == 0.0
    assert poisson_at_least(5.0, 0) == 1.0
    brute = 1 - sum(math.exp(-8) * 8 ** k / math.factorial(k) for k in range(10))
    assert poisson_at_least(8.0, 10) == pytest.approx(brute)


def test_goalkeepers_cannot_earn_them():
    assert hit_probability("GKP", total=50, minutes=900, position_rate=5.0) == 0.0


def test_busy_defender_likely_to_hit():
    busy = hit_probability("DEF", total=140, minutes=900, position_rate=8.0)  # 14 per 90
    quiet = hit_probability("DEF", total=40, minutes=900, position_rate=8.0)  # 4 per 90
    assert busy > 0.8
    assert quiet < 0.05


def test_little_playing_time_leans_on_position_average():
    # 1 match of 20 actions shouldn't make someone a near-certainty.
    one_big_game = hit_probability("DEF", total=20, minutes=90, position_rate=8.0)
    position_average = hit_probability("DEF", total=0, minutes=0, position_rate=8.0)
    assert position_average < one_big_game < 0.9


def _history(rows):
    return pd.DataFrame(rows, columns=["element", "position", "gameweek", "minutes", "defensive_contribution"])


def test_evaluate_never_uses_the_gameweek_being_predicted():
    def season(gw3_count):
        rows = [(1, "DEF", gw, 90, 11) for gw in (1, 2)] + [(1, "DEF", 3, 90, gw3_count)]
        rows += [(2, "DEF", gw, 90, 5) for gw in (1, 2, 3)]
        return _history(rows)

    normal = evaluate(season(11), gameweeks=[3])
    changed = evaluate(season(0), gameweeks=[3])
    for column in ("p_rate", "p_history", "p_position"):
        pd.testing.assert_series_equal(normal[column], changed[column])
    assert normal["hit"].tolist() == [1, 0]
    assert changed["hit"].tolist() == [0, 0]


def test_evaluate_only_scores_60_minute_appearances():
    rows = [(1, "MID", 1, 90, 12), (1, "MID", 2, 30, 3), (1, "MID", 3, 90, 13)]
    result = evaluate(_history(rows), gameweeks=[2, 3])
    assert result["gameweek"].tolist() == [3]
