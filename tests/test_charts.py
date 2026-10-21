"""Tests for the Season charts (src/charts.py) - checks the design rules hold."""

import pandas as pd
import pytest

from src.charts import THEMES, points_chart, positions_chart, rank_chart

WEEKS = pd.DataFrame({"gameweek": [1, 2], "points": [60, 40], "average": [50, 45],
                      "highest": [120, 110], "overall_rank": [500, 2000], "gw_rank": [500, 9000]})
POSITIONS = pd.DataFrame({"gameweek": [1] * 4, "position": ["GKP", "DEF", "MID", "FWD"],
                          "points": [6, 10, 30, 14]})


def _find(spec, key):
    """Every value stored under `key`, anywhere in a nested chart spec."""
    found = []
    if isinstance(spec, dict):
        for k, v in spec.items():
            if k == key:
                found.append(v)
            found.extend(_find(v, key))
    elif isinstance(spec, list):
        for item in spec:
            found.extend(_find(item, key))
    return found


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_position_colours_are_fixed_per_position(mode):
    # GKP is always slot 1, DEF slot 2... regardless of which positions scored.
    spec = positions_chart(POSITIONS, mode).to_dict()
    scale = next(s for s in _find(spec, "scale") if "domain" in s)
    assert scale["domain"] == ["GKP", "DEF", "MID", "FWD"]
    assert scale["range"] == THEMES[mode]["series"]


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_rank_axis_is_flipped_and_log(mode):
    spec = rank_chart(WEEKS, mode).to_dict()
    scale = next(s for s in _find(spec, "scale") if s.get("type") == "log")
    assert scale["reverse"] is True  # up = better rank


def test_your_line_is_the_coloured_one():
    # Average and top score are grey reference lines; only "You" uses a series colour.
    spec = points_chart(WEEKS, "dark").to_dict()
    scale = next(s for s in _find(spec, "scale") if s.get("domain") == ["You", "FPL average", "Top score"])
    you, average, top = scale["range"]
    assert you == THEMES["dark"]["series"][0]
    assert average == THEMES["dark"]["secondary"] and top == THEMES["dark"]["muted"]
