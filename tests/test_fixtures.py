"""Tests for the upcoming-fixtures grid (src/fixtures.py)."""

import pandas as pd
import pytest

from src.fixtures import build_grid, cell_colour, fixture_score
from src.team_strength import TeamStrengths

# Three teams: Strong (scores lots, concedes little), Average, Weak.
STRENGTHS = TeamStrengths(
    table=pd.DataFrame({"attack": [1.5, 1.0, 0.6], "defence_weakness": [0.6, 1.0, 1.5]},
                       index=["Strong", "Average", "Weak"]),
    home_rate=1.5, away_rate=1.2,
)
SHORT = {"Strong": "STR", "Average": "AVG", "Weak": "WEA"}


def _fixture(gw, home, away):
    return {"event": gw, "home": home, "away": away}


def test_grid_has_each_teams_opponents_per_gameweek():
    fixtures = [_fixture(8, "Strong", "Weak"), _fixture(9, "Average", "Strong"), _fixture(9, "Weak", "Average")]
    grid = build_grid(fixtures, STRENGTHS, SHORT, gameweeks=[8, 9])
    strong = grid[(grid["team"] == "Strong")]
    gw8 = strong[strong["gameweek"] == 8].iloc[0]
    assert gw8["label"] == "WEA (H)"
    # Strong at home to Weak: 1.5 x 1.5 x 1.5 = 3.375 expected goals for, 1.2 x 0.6 x 0.6 against.
    assert gw8["xg_for"] == pytest.approx(3.375)
    assert gw8["xg_against"] == pytest.approx(0.432)
    assert strong[strong["gameweek"] == 9].iloc[0]["label"] == "AVG (A)"


def test_blank_and_double_gameweeks():
    fixtures = [_fixture(8, "Strong", "Weak"), _fixture(8, "Average", "Strong")]  # Strong plays twice
    grid = build_grid(fixtures, STRENGTHS, SHORT, gameweeks=[8, 9])
    strong8 = grid[(grid["team"] == "Strong") & (grid["gameweek"] == 8)].iloc[0]
    assert strong8["matches"] == 2
    assert strong8["label"] == "WEA (H), AVG (A)"
    strong9 = grid[(grid["team"] == "Strong") & (grid["gameweek"] == 9)].iloc[0]
    assert strong9["matches"] == 0
    assert strong9["label"] == "—"


def test_fixture_score_is_relative_to_an_average_match():
    # Attack: expected goals vs the league's average per match; defence: clean-sheet chance vs average.
    assert fixture_score(1.35, average=1.35) == pytest.approx(0.0)
    assert fixture_score(2.7, average=1.35) > 0     # twice the average -> good
    assert fixture_score(0.675, average=1.35) < 0   # half -> bad
    assert fixture_score(2.7, average=1.35) == pytest.approx(-fixture_score(0.675, average=1.35))
    assert fixture_score(0.0, average=1.35) == pytest.approx(-1.0)  # blank: clipped to the worst


def test_cell_colour_green_good_red_bad_grey_neutral():
    assert "0, 131, 0" in cell_colour(0.8, mode="light")       # green = good
    assert "227, 73, 72" in cell_colour(-0.8, mode="light")    # red = hard
    assert cell_colour(0.0, mode="light") == cell_colour(0.01, mode="light")  # tiny = neutral
    strong, weak = cell_colour(1.0, mode="dark"), cell_colour(0.3, mode="dark")
    assert strong != weak  # stronger tint further from average
