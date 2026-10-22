"""Tests for the predicted-vs-actual track record (src/track_record.py)."""

import pandas as pd
import pytest

from src.track_record import gameweeks_to_rebuild, pick_source, score_gameweek, squad_prediction


def test_score_gameweek_uses_players_who_played():
    predictions = pd.DataFrame({"id": [1, 2, 3, 4], "projected_points": [6.0, 4.0, 2.0, 3.0]})
    actual = pd.DataFrame({"id": [1, 2, 3, 4], "points": [9, 5, 1, 0], "minutes": [90, 90, 90, 0]})
    result = score_gameweek(predictions, actual)
    assert result["players"] == 3                       # player 4 didn't play
    assert result["rank_corr"] == pytest.approx(1.0)    # perfect order among those who played
    assert result["predicted_avg"] == pytest.approx(4.0)
    assert result["actual_avg"] == pytest.approx(5.0)
    assert result["mae"] == pytest.approx((3 + 1 + 1) / 3)


def test_squad_prediction_follows_the_real_lineup():
    # Captain (x2) counts double, bench (x0) doesn't count - same as FPL scoring.
    picks = [{"element": 1, "multiplier": 2}, {"element": 2, "multiplier": 1},
             {"element": 3, "multiplier": 0}]
    predictions = pd.DataFrame({"id": [1, 2, 3], "projected_points": [6.0, 4.0, 5.0]})
    assert squad_prediction(picks, predictions) == pytest.approx(16.0)


def test_saved_snapshot_preferred_over_rebuilt():
    saved = pd.DataFrame({"id": [1], "projected_points": [5.0]})
    rebuilt = pd.DataFrame({"id": [1], "projected_points": [4.0]})
    predictions, source = pick_source(saved, rebuilt)
    assert source == "saved at deadline"
    assert predictions["projected_points"].iloc[0] == 5.0
    assert pick_source(None, rebuilt)[1] == "rebuilt"
    assert pick_source(None, None) == (None, None)


def test_gameweeks_to_rebuild_are_finished_and_missing():
    events = [{"id": gw, "finished": gw <= 7} for gw in range(1, 10)]
    # GW1-2 have too little history to predict from; GW3 and GW4 already done.
    assert gameweeks_to_rebuild(events, already_saved={3, 4}) == [5, 6, 7]
