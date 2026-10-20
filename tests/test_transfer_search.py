"""
Tests for searching transfers and deciding whether a -4 hit pays off
(src/transfers.py: search_transfers, plan_transfers).

Worked by hand on the test squad (FULL_SQUAD in conftest.py), £1.0m in the bank.
Best XI now: 4-4-2 = 4 GK + 13 DEF + 17 MID + 11 FWD = 45, + Haaland's 8 as captain = 53.0
- DefE (1.0) -> DefF (6.5, +£1.0m):  4-4-2 = 4 + 17 + 17 + 11 = 49 -> 57.0   (+4.0)  best single
  (DefD -> DefF ties at +4.0: whichever cheap defender goes, he'd be benched anyway)
- Palmer (0, injured) -> Saka (6, -£0.2m):  3-5-2 = 4 + 10.5 + 23 + 11 = 48.5 -> 56.5  (+3.5)
- Both: 3-5-2 = 4 + 14 + 23 + 11 = 52 -> 60.0  (+7.0). DefF can be funded by
  selling DefE (£4.0m) or DefC (£4.5m) - both reach 60.0, so either is a valid answer.
"""

import pytest

from src.transfers import plan_transfers, search_transfers
from tests.conftest import FULL_SQUAD, make_squad

LIMITS = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}


def _search(players, bank=1.0, squad_ids=FULL_SQUAD):
    squad = make_squad(players, squad_ids, captain_id=4)
    return search_transfers(squad, players, bank=bank, limits=LIMITS, club_limit=3)


def test_best_single_transfer_per_player(players):
    singles = _search(players)["singles"]
    by_out = singles.set_index("out_name")
    assert by_out.loc["DefE", "in_name"] == "DefF"
    assert by_out.loc["DefE", "gain"] == pytest.approx(4.0)
    assert by_out.loc["Palmer", "in_name"] == "Saka"
    assert by_out.loc["Palmer", "gain"] == pytest.approx(3.5)
    assert singles.iloc[0]["gain"] == pytest.approx(4.0)  # ranked best first (DefD/DefE tie)
    assert singles.iloc[0]["in_name"] == "DefF"


def test_best_pair_funds_both_upgrades(players):
    pair = _search(players)["best_pair"]
    assert set(pair["in_names"]) == {"Saka", "DefF"}
    assert "Palmer" in pair["out_names"]
    assert pair["gain"] == pytest.approx(7.0)
    assert pair["formation_after"] == "3-5-2"


def test_pair_respects_combined_budget(players):
    # Make DefF cost £20m: no combination of two sales can fund him
    # (the most any sale frees is £2.4m: B.Fernandes -> Saka).
    players.loc[players["web_name"] == "DefF", "now_cost"] = 20.0
    result = _search(players)
    assert "DefF" not in result["best_pair"]["in_names"]
    assert "DefF" not in set(result["singles"]["in_name"])


def _clubs_after(players, squad_ids, out_ids, in_ids):
    final = (set(squad_ids) - set(out_ids)) | set(in_ids)
    return players[players["id"].isin(final)]["team"].value_counts()


def test_club_limit_applies_to_pairs(players):
    # Squad already has Raya + Saliba (Arsenal). The search may still buy two
    # Arsenal players if it sells one (e.g. Saliba) - but never ends above 3.
    squad = [5, 18, 11, 12, 13, 14, 19, 1, 3, 6, 7, 10, 4, 8, 17]
    pair = _search(players, squad_ids=squad)["best_pair"]
    assert _clubs_after(players, squad, pair["out_ids"], pair["in_ids"]).max() <= 3
    tight = make_squad(players, squad, captain_id=4)
    strict = search_transfers(tight, players, bank=1.0, limits=LIMITS, club_limit=2)["best_pair"]
    assert _clubs_after(players, squad, strict["out_ids"], strict["in_ids"]).max() <= 2


def test_one_free_transfer_hit_not_worth_it(players):
    # Single: +4.0 free. Pair: +7.0 - 4 = +3.0. The hit costs more than it gains.
    plan = plan_transfers(_search(players), free_transfers=1)
    assert plan["recommended"] == "single"
    assert plan["options"]["pair"]["net"] == pytest.approx(3.0)
    assert plan["hit_worth_it"] is False


def test_two_free_transfers_makes_the_pair_free(players):
    plan = plan_transfers(_search(players), free_transfers=2)
    assert plan["recommended"] == "pair"
    assert plan["options"]["pair"]["net"] == pytest.approx(7.0)
    assert plan["hit_worth_it"] is None  # no hit involved


def test_no_free_transfers_means_every_transfer_costs_4(players):
    plan = plan_transfers(_search(players), free_transfers=0)
    assert plan["options"]["single"]["net"] == pytest.approx(4.0 - 4)
    assert plan["options"]["pair"]["net"] == pytest.approx(7.0 - 8)
    assert plan["recommended"] == "none"  # a tie with the single goes to fewer transfers


def test_hit_worth_it_when_the_second_transfer_gains_more_than_4(players):
    # Saka 12 and DefF 9. Best single: Palmer -> Saka, 3-5-2 = 54.5 + Saka 12 as
    # captain = 66.5 (+13.5). Both: 60.5 + 12 = 72.5 (+19.5). The second transfer
    # adds 6.0 - more than the 4-point hit.
    players.loc[players["web_name"] == "Saka", "projected_points"] = 12.0
    players.loc[players["web_name"] == "DefF", "projected_points"] = 9.0
    plan = plan_transfers(_search(players), free_transfers=1)
    assert plan["options"]["single"]["gain"] == pytest.approx(13.5)
    assert plan["options"]["pair"]["gain"] == pytest.approx(19.5)
    assert plan["recommended"] == "pair"
    assert plan["hit_worth_it"] is True
