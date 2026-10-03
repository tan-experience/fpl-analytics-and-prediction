"""
Tests for the backtest (src/backtest.py).

The most important property here is "no leakage": when projecting a match,
the backtest must only use matches BEFORE it. If that ever broke, every
accuracy number would silently look better than reality - so it gets
several tests.
"""

import math

import pandas as pd

from src.backtest import FORM_WINDOW, add_before_match_features, project, score


def _matches(element: int, points: list) -> pd.DataFrame:
    """One player's matches, one per week, in order, with the given points."""
    return pd.DataFrame({
        "element": element,
        "kickoff_time": [f"2026-08-{10 + 7 * i:02d}T15:00:00Z" for i in range(len(points))],
        "total_points": points,
    })


def test_first_match_has_no_history():
    result = add_before_match_features(_matches(1, [5, 3]))
    assert math.isnan(result.loc[0, "form_before"])
    assert result.loc[0, "prior_matches"] == 0


def test_form_uses_only_earlier_matches():
    result = add_before_match_features(_matches(1, [2, 4, 6, 8, 10]))
    # Match 2 sees only match 1; match 5 sees matches 1-4.
    assert result.loc[1, "form_before"] == 2
    assert result.loc[4, "form_before"] == (2 + 4 + 6 + 8) / 4
    assert list(result["prior_matches"]) == [0, 1, 2, 3, 4]


def test_changing_a_result_does_not_change_its_own_or_earlier_projections():
    # The core "no leakage" check: if a player had scored 20 instead of 10
    # in their last match, nothing projected for that match or earlier
    # should change - those projections couldn't have known.
    normal = add_before_match_features(_matches(1, [2, 4, 6, 8, 10]))
    changed = add_before_match_features(_matches(1, [2, 4, 6, 8, 20]))
    pd.testing.assert_series_equal(normal["form_before"], changed["form_before"])
    pd.testing.assert_series_equal(normal["season_avg_before"], changed["season_avg_before"])


def test_form_window_drops_old_matches_but_season_average_keeps_them():
    points = [10] + [2] * FORM_WINDOW + [0]  # one big early haul, then quiet
    result = add_before_match_features(_matches(1, points)).iloc[-1]
    assert result["form_before"] == 2  # the 10 has dropped out of the window
    assert result["season_avg_before"] == (10 + 2 * FORM_WINDOW) / (1 + FORM_WINDOW)


def test_players_do_not_share_history():
    both = pd.concat([_matches(1, [10, 10]), _matches(2, [0, 0])])
    result = add_before_match_features(both).set_index(["element", "prior_matches"])
    assert result.loc[(1, 1), "form_before"] == 10
    assert result.loc[(2, 1), "form_before"] == 0


def test_rows_out_of_order_are_sorted_by_kickoff():
    shuffled = _matches(1, [2, 4, 6]).iloc[[2, 0, 1]]
    result = add_before_match_features(shuffled)
    assert list(result["total_points"]) == [2, 4, 6]
    assert result.loc[2, "form_before"] == 3


def test_project_formula():
    # Easy fixture (difficulty 1) is 2 steps below average (3): +2 x weight.
    form = pd.Series([4.0])
    assert project(form, pd.Series([1]), weight=0.5).iloc[0] == 5.0
    assert project(form, pd.Series([5]), weight=0.5).iloc[0] == 3.0


def test_score_perfect_order_and_error():
    table = pd.DataFrame({"gameweek": [1, 1, 1], "actual_points": [1, 5, 9]})
    result = score(pd.Series([2, 6, 10]), table)
    assert result["rank_corr"] == 1.0  # right order
    assert result["mae"] == 1.0  # each off by exactly 1


def test_score_constant_prediction_has_no_rank_correlation():
    table = pd.DataFrame({"gameweek": [1, 1, 1], "actual_points": [1, 5, 9]})
    result = score(pd.Series([2.0, 2.0, 2.0]), table)
    assert math.isnan(result["rank_corr"])
