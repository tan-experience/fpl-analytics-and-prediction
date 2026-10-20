"""
Tests for transfer suggestions and the what-if simulator (src/transfers.py).

These functions normally fetch your squad and bank balance from the FPL
API. `monkeypatch` (built into pytest) temporarily swaps those functions
for fake ones that return our test data, just for the duration of a test.
"""

import pytest

from src import transfers
from tests.conftest import FULL_SQUAD, make_squad

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
    monkeypatch.setattr(transfers, "get_projections", lambda: players)
    monkeypatch.setattr(transfers, "squad_limits",
                        lambda: {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)})
    monkeypatch.setattr(transfers, "CLUB_LIMIT", 3)

    def set_squad(squad):
        state["squad"] = squad
    return set_squad


def test_suggestions_ranked_by_best_xi_gain_with_reasons(fake_api, players):
    # See test_transfer_search.py for the worked numbers on this squad.
    fake_api(make_squad(players, FULL_SQUAD, captain_id=4))
    # Top 5: DefD/DefE -> DefF tie at +4.0; DefC -> DefF and Palmer -> Saka tie at +3.5.
    suggestions = transfers.suggest_transfers(team_id=1, max_suggestions=5)
    assert suggestions[0]["in_name"] == "DefF"
    assert suggestions[0]["gain"] == pytest.approx(4.0)
    palmer = next(s for s in suggestions if s["out_name"] == "Palmer")
    assert palmer["in_name"] == "Saka"
    assert palmer["reason"] == "Palmer isn't expected to play"
    assert suggestions[0]["reason"].startswith("DefF projects 6.5 pts vs")


def test_no_suggestions_when_nothing_improves_the_best_xi(fake_api, players):
    # Nobody outside the squad is projected to score: nothing worth buying.
    players.loc[~players["id"].isin(FULL_SQUAD), "projected_points"] = 0.0
    fake_api(make_squad(players, FULL_SQUAD, captain_id=4))
    assert transfers.suggest_transfers(team_id=1) == []


def test_simulate_judges_by_best_xi_and_formation(fake_api, players):
    # Palmer (injured, 0 pts, on the bench in the best XI) -> Saka (6 pts).
    # Before: best is 4-4-2 (45 + Haaland's 8 as captain = 53).
    # After:  Saka makes a 5-strong midfield worth it -> 3-5-2 (48.5 + 8 = 56.5);
    #         DefD drops out of the XI. Slot-swapping would have missed this.
    fake_api(make_squad(players, FULL_SQUAD, captain_id=4))
    result = transfers.simulate_transfer(team_id=1, out_player_id=1, in_player_id=2)
    assert result["before"]["formation"] == "4-4-2"
    assert result["after"]["formation"] == "3-5-2"
    assert result["old_starting_total"] == pytest.approx(53.0)
    assert result["new_starting_total"] == pytest.approx(56.5)
    assert result["projected_gain"] == pytest.approx(3.5)
    assert result["joins_xi"] == ["Saka"]
    assert result["leaves_xi"] == ["DefD"]
    assert result["formations_after"].iloc[0]["formation"] == "3-5-2"
    assert result["cost_diff"] == -0.2


def test_simulate_rejects_a_fourth_player_from_one_club(fake_api, players):
    # Raya, Saliba and DefF are all Arsenal; Saka would be a 4th.
    squad = [5, 18, 11, 12, 13, 16, 19, 1, 3, 6, 7, 10, 4, 8, 17]
    fake_api(make_squad(players, squad, captain_id=4))
    with pytest.raises(ValueError, match="at most 3 from one club"):
        transfers.simulate_transfer(team_id=1, out_player_id=1, in_player_id=2)


def test_simulate_rejects_position_mismatch(fake_api, players):
    fake_api(make_squad(players, FULL_SQUAD, captain_id=4))
    with pytest.raises(ValueError, match="Position mismatch"):
        transfers.simulate_transfer(team_id=1, out_player_id=4, in_player_id=9)  # FWD -> GKP


def test_simulate_rejects_over_budget(fake_api, players):
    fake_api(make_squad(players, FULL_SQUAD, captain_id=4))
    with pytest.raises(ValueError, match="Not enough budget"):
        transfers.simulate_transfer(team_id=1, out_player_id=3, in_player_id=2)  # +£1.6m, £1.0m bank


def test_simulate_rejects_player_already_owned(fake_api, players):
    # The message should name the player, not show an internal ID.
    fake_api(make_squad(players, FULL_SQUAD, captain_id=4))
    with pytest.raises(ValueError, match="^Mbeumo is already in this squad"):
        transfers.simulate_transfer(team_id=1, out_player_id=1, in_player_id=3)


def test_simulate_rejects_selling_player_not_owned(fake_api, players):
    fake_api(make_squad(players, FULL_SQUAD, captain_id=4))
    with pytest.raises(ValueError, match="^Saka isn't in this squad"):
        transfers.simulate_transfer(team_id=1, out_player_id=2, in_player_id=10)
