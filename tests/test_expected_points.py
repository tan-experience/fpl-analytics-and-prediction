"""Tests for the combined expected points model (src/expected_points.py)."""

import pandas as pd
import pytest

from src.expected_points import actual_components, evaluate

SCORING = {
    "clean_sheets": {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0},
    "goals_conceded": {"GKP": -1, "DEF": -1, "MID": 0, "FWD": 0},
    "goals_scored": {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4},
    "assists": 3,
    "defensive_contribution": {"GKP": 0, "DEF": 2, "MID": 2, "FWD": 2},
}

COLUMNS = [
    "element", "position", "team", "fixture", "gameweek", "kickoff_time", "minutes", "starts",
    "total_points", "goals_scored", "assists", "clean_sheets", "goals_conceded", "bonus", "saves",
    "defensive_contribution", "expected_goals", "expected_assists",
    "opponent_expected_goals", "opponent_factor", "difficulty",
]


def _row(element, position, gw, **overrides):
    row = dict(element=element, position=position, team="A", fixture=gw * 10 + element,
               gameweek=gw, kickoff_time=f"2026-08-{gw * 7:02d}T15:00:00Z", minutes=90, starts=1,
               total_points=2, goals_scored=0, assists=0, clean_sheets=0, goals_conceded=1,
               bonus=0, saves=0, defensive_contribution=5, expected_goals=0.1,
               expected_assists=0.1, opponent_expected_goals=1.3, opponent_factor=1.0, difficulty=3)
    row.update(overrides)
    return row


def test_actual_components_add_up_for_a_typical_defender():
    # 90 mins, clean sheet, 11 defensive actions, 1 bonus = 2 + 4 + 2 + 1 = 9.
    row = pd.Series(_row(1, "DEF", 1, clean_sheets=1, goals_conceded=0,
                         defensive_contribution=11, bonus=1, total_points=9))
    parts = actual_components(row, SCORING)
    assert parts == {"appearance": 2, "clean_sheet_and_conceded": 4, "defensive_contribution": 2,
                     "goals_and_assists": 0, "bonus": 1, "saves": 0, "other": 0}


def test_actual_components_goalkeeper_saves_and_conceded():
    # 90 mins, conceded 3 (-1), 7 saves (+2), total 3.
    row = pd.Series(_row(1, "GKP", 1, goals_conceded=3, saves=7, defensive_contribution=0, total_points=3))
    parts = actual_components(row, SCORING)
    assert parts["clean_sheet_and_conceded"] == -1
    assert parts["saves"] == 2
    assert parts["other"] == 0


def test_actual_components_other_catches_cards():
    # Yellow card: FPL total is 1 less than the parts we model.
    row = pd.Series(_row(1, "MID", 1, total_points=1))
    assert actual_components(row, SCORING)["other"] == -1


def _season(gw3_points, gw3_goals, gw3_xg=0.6, gw3_bonus=0, gw3_dc=5, gw3_starts=1):
    rows = []
    for gw in (1, 2):
        rows.append(_row(1, "FWD", gw, goals_scored=1, total_points=6, expected_goals=0.6))
        rows.append(_row(2, "DEF", gw, clean_sheets=1, goals_conceded=0, total_points=6))
    rows.append(_row(1, "FWD", 3, goals_scored=gw3_goals, total_points=gw3_points,
                     expected_goals=gw3_xg, bonus=gw3_bonus))
    rows.append(_row(2, "DEF", 3, total_points=2, defensive_contribution=gw3_dc, starts=gw3_starts))
    return pd.DataFrame(rows, columns=COLUMNS)


def test_evaluate_never_uses_the_gameweek_being_predicted():
    normal = evaluate(_season(6, 1), gameweeks=[3], scoring=SCORING)
    # Change everything the model reads, not just the result - otherwise a
    # leak could go unnoticed (the model predicts from xG and bonus, not goals).
    changed = evaluate(_season(14, 3, gw3_xg=2.5, gw3_bonus=3, gw3_dc=15, gw3_starts=0),
                       gameweeks=[3], scoring=SCORING)
    for column in ("predicted", "old_formula"):
        pd.testing.assert_series_equal(normal[column], changed[column])
    assert changed["actual"].tolist() == [14, 2]


def test_evaluate_components_sum_to_prediction():
    rows = evaluate(_season(6, 1), gameweeks=[3], scoring=SCORING)
    parts = [c for c in rows.columns if c.startswith("pred_")]
    assert rows[parts].sum(axis=1).tolist() == pytest.approx(rows["predicted"].tolist())
