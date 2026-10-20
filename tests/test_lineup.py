"""Tests for picking the best starting XI and formation (src/lineup.py)."""

import pandas as pd
import pytest

from src.lineup import best_xi, formation_options, valid_formations

LIMITS = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}


def _squad(points: dict) -> pd.DataFrame:
    """points: {position: [projected points for each player in that position]}"""
    rows, pid = [], 1
    for position, values in points.items():
        for value in values:
            rows.append({"id": pid, "web_name": f"{position}{pid}", "position": position,
                         "projected_points": value})
            pid += 1
    return pd.DataFrame(rows)


# A normal 15: 2 GKP, 5 DEF, 5 MID, 3 FWD
BALANCED = {"GKP": [4, 3], "DEF": [5, 4, 4, 3, 1], "MID": [6, 5, 4, 3, 2], "FWD": [7, 4, 1]}


def test_valid_formations_are_fpls_eight():
    assert sorted(valid_formations(LIMITS)) == sorted([
        (3, 4, 3), (3, 5, 2), (4, 3, 3), (4, 4, 2), (4, 5, 1), (5, 2, 3), (5, 3, 2), (5, 4, 1)])


def test_best_xi_picks_highest_formation_and_captain():
    result = best_xi(_squad(BALANCED), LIMITS)
    # Best 11: GK 4; DEF 5,4,4; MID 6,5,4; FWD 7,4 -> 3-4-3 needs a 4th MID (3) and 3rd FWD (1)...
    # every formation is checked; 4-4-2 = 4 + (5+4+4+3) + (6+5+4+3) + (7+4) = 49
    assert result["formation"] == "4-4-2"
    assert result["total_before_captain"] == pytest.approx(49)
    # Captain = top projected starter (7), whose points count twice.
    assert result["captain"] == result["xi"].loc[result["xi"]["projected_points"].idxmax(), "id"]
    assert result["total"] == pytest.approx(49 + 7)


def test_bench_has_the_other_four_with_goalkeeper_first():
    result = best_xi(_squad(BALANCED), LIMITS)
    assert len(result["xi"]) == 11
    assert len(result["bench"]) == 4
    assert result["bench"].iloc[0]["position"] == "GKP"  # FPL's bench order: sub keeper first
    assert set(result["xi"]["id"]) | set(result["bench"]["id"]) == set(range(1, 16))


def test_strong_midfield_changes_the_formation():
    # 3-5-2 = 4 + (5+1+1) + 30 + (7+2) = 50, ahead of 4-5-1 (49) - no ties.
    strong_mid = {"GKP": [4, 3], "DEF": [5, 1, 1, 1, 1], "MID": [6, 6, 6, 6, 6], "FWD": [7, 2, 1]}
    assert best_xi(_squad(strong_mid), LIMITS)["formation"] == "3-5-2"


def test_choosing_a_formation_yourself():
    result = best_xi(_squad(BALANCED), LIMITS, formation=(3, 5, 2))
    assert result["formation"] == "3-5-2"
    assert (result["xi"]["position"] == "MID").sum() == 5


def test_formation_options_lists_every_formation_best_first():
    options = formation_options(_squad(BALANCED), LIMITS)
    assert len(options) == 8
    assert options.iloc[0]["formation"] == "4-4-2"
    assert options["total"].is_monotonic_decreasing


def test_fast_total_matches_best_xi():
    # best_total() is the quick version used when searching thousands of
    # transfer combinations - it must agree with the full best_xi().
    from src.lineup import best_total
    for squad in (BALANCED, {"GKP": [4, 3], "DEF": [5, 1, 1, 1, 1], "MID": [6, 6, 6, 6, 6], "FWD": [7, 2, 1]}):
        frame = _squad(squad)
        points = {pos: frame.loc[frame["position"] == pos, "projected_points"].tolist() for pos in squad}
        assert best_total(points, LIMITS) == pytest.approx(best_xi(frame, LIMITS)["total"])
