"""Tests for the season overview (src/season.py)."""

import pandas as pd
import pytest

from src.season import gameweek_breakdown, insights, weekly_table

POSITIONS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD", 5: "MID"}


def test_breakdown_uses_multipliers_as_fpl_reports_them():
    # FPL's picks already include automatic subs and chips in the multiplier:
    # 0 = benched (or subbed off), 1 = counts, 2 = captain, 3 = triple captain.
    picks = [
        {"element": 1, "multiplier": 1, "is_captain": False},
        {"element": 2, "multiplier": 1, "is_captain": False},
        {"element": 3, "multiplier": 2, "is_captain": True},
        {"element": 4, "multiplier": 1, "is_captain": False},
        {"element": 5, "multiplier": 0, "is_captain": False},  # on the bench
    ]
    live = {1: 6, 2: 2, 3: 8, 4: 5, 5: 11}
    result = gameweek_breakdown(picks, live, POSITIONS)
    assert result["by_position"] == {"GKP": 6, "DEF": 2, "MID": 16, "FWD": 5}
    assert result["total"] == 29
    assert result["captain_id"] == 3
    assert result["captain_points"] == 16      # 8 x 2
    assert result["bench_points"] == 11        # benched players' points, not counted


def test_triple_captain():
    picks = [{"element": 3, "multiplier": 3, "is_captain": True}]
    result = gameweek_breakdown(picks, {3: 10}, POSITIONS)
    assert result["captain_points"] == 30


def _history_rows():
    return [
        {"event": 1, "points": 60, "total_points": 60, "rank": 500, "overall_rank": 500,
         "value": 1000, "bank": 0, "event_transfers": 0, "event_transfers_cost": 0, "points_on_bench": 3},
        {"event": 2, "points": 40, "total_points": 96, "rank": 9000, "overall_rank": 2000,
         "value": 1003, "bank": 5, "event_transfers": 2, "event_transfers_cost": 4, "points_on_bench": 12},
    ]


def test_weekly_table_joins_history_with_averages_and_chips():
    events = [{"id": 1, "average_entry_score": 50, "highest_score": 120},
              {"id": 2, "average_entry_score": 45, "highest_score": 110}]
    chips = [{"name": "bboost", "event": 2}]
    table = weekly_table(_history_rows(), events, chips)
    assert table["gameweek"].tolist() == [1, 2]
    assert table["average"].tolist() == [50, 45]
    assert table["beat_average"].tolist() == [True, False]
    assert table["chip"].tolist() == ["", "Bench Boost"]
    assert table["hit_cost"].tolist() == [0, 4]


def test_insights_in_plain_words():
    events = [{"id": 1, "average_entry_score": 50, "highest_score": 120},
              {"id": 2, "average_entry_score": 45, "highest_score": 110}]
    table = weekly_table(_history_rows(), events, [])
    table["captain_points"] = [20, 4]
    lines = insights(table)
    assert "You beat the average in 1 of 2 gameweeks." in lines
    assert "15 points left on the bench." in lines
    assert "-4 in transfer hits." in lines
    assert any(line.startswith("Captain picks: 24 points") for line in lines)
