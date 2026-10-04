"""
Tests for transfer suggestions and the what-if simulator (src/transfers.py).

These functions normally fetch your squad and bank balance from the FPL
API. `monkeypatch` (built into pytest) temporarily swaps those functions
for fake ones that return our test data, just for the duration of a test.
"""

import pytest

from src import transfers
from tests.conftest import make_squad

BANK = 1.0  # £1.0m in the bank for every test


@pytest.fixture
def fake_api(monkeypatch, players):
    """
    Replaces the API-calling functions transfers.py uses. Returns a function
    to set which squad the "API" reports.
    """
    state = {"squad": None}
    monkeypatch.setattr(transfers, "get_squad_projection", lambda team_id, gw=None: (state["squad"], 5))
    monkeypatch.setattr(transfers, "_get_bank", lambda team_id: BANK)
    monkeypatch.setattr(transfers, "build_player_features", lambda: players)
    monkeypatch.setattr(transfers, "project_gameweek_points", lambda df: df)

    def set_squad(squad):
        state["squad"] = squad
    return set_squad


def test_injured_starter_is_flagged(fake_api, players):
    # Palmer (id 1) is injured and projected 0 - this was the original bug:
    # he was never suggested because his fixtures weren't "tough".
    fake_api(make_squad(players, [1, 3, 4], captain_id=4))
    suggestions = transfers.suggest_transfers(team_id=1)
    assert suggestions[0]["out_name"] == "Palmer"
    assert suggestions[0]["reason"] == "not expected to play"
    assert suggestions[0]["in_name"] == "Saka"  # best affordable MID


def test_healthy_squad_gets_no_suggestions(fake_api, players):
    # Mbeumo and Haaland: available, decent projections, easy fixtures.
    fake_api(make_squad(players, [3, 4], captain_id=4))
    assert transfers.suggest_transfers(team_id=1) == []


def test_weak_player_with_tough_run_is_flagged(fake_api, players):
    # Make Mbeumo poor (1 pt, below the MID average) with a brutal run ahead.
    players.loc[players["id"] == 3, ["projected_points", "next_3_avg_difficulty"]] = [1.0, 4.5]
    players.loc[players["id"] == 1, ["projected_points", "status"]] = [4.0, "a"]  # Palmer healthy
    fake_api(make_squad(players, [1, 3, 4], captain_id=4))
    suggestions = transfers.suggest_transfers(team_id=1)
    assert [s["out_name"] for s in suggestions] == ["Mbeumo"]
    assert suggestions[0]["reason"] == "tough run + below position average"


def test_suggestions_respect_budget(fake_api, players):
    # B.Fernandes (£11.9m) would be too expensive for Palmer (£9.7m) + £1.0m bank.
    fake_api(make_squad(players, [1, 3, 4], captain_id=4))
    suggested_in = {s["in_name"] for s in transfers.suggest_transfers(team_id=1)}
    assert "B.Fernandes" not in suggested_in


def test_simulate_valid_transfer(fake_api, players):
    fake_api(make_squad(players, [1, 3, 4], captain_id=4))
    result = transfers.simulate_transfer(team_id=1, out_player_id=1, in_player_id=2)
    assert result["projected_gain"] == 6.0  # Palmer 0 -> Saka 6
    assert result["cost_diff"] == -0.2
    assert result["remaining_bank"] == pytest.approx(BANK + 0.2)


def test_simulate_rejects_position_mismatch(fake_api, players):
    fake_api(make_squad(players, [1, 3, 4], captain_id=4))
    with pytest.raises(ValueError, match="Position mismatch"):
        transfers.simulate_transfer(team_id=1, out_player_id=4, in_player_id=5)  # FWD -> GKP


def test_simulate_rejects_over_budget(fake_api, players):
    fake_api(make_squad(players, [1, 3, 4], captain_id=4))
    with pytest.raises(ValueError, match="Not enough budget"):
        transfers.simulate_transfer(team_id=1, out_player_id=3, in_player_id=6)  # +£4.0m


def test_simulate_rejects_player_already_owned(fake_api, players):
    fake_api(make_squad(players, [1, 3, 4], captain_id=4))
    with pytest.raises(ValueError, match="already in this squad"):
        transfers.simulate_transfer(team_id=1, out_player_id=1, in_player_id=3)
