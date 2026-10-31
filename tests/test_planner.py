"""
Tests for the multi-week transfer planner (src/planner.py).

1. Over ONE week it must agree with the existing transfer search
   (no transfer / best single / best pair), which is tested separately.
2. A made-up case where rolling is clearly right: it must roll now and
   make two transfers next week.
3. FPL's rules hold in every week of every plan.
"""

import pandas as pd
import pytest

from src.planner import plan_weeks
from src.transfers import plan_transfers, search_transfers
from tests.conftest import FULL_SQUAD, make_squad

LIMITS = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}
SIZES = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}


def _plan(players, weeks, free_transfers, squad_ids=FULL_SQUAD, bank=1.0, **kwargs):
    return plan_weeks(players, squad_ids, bank, weeks, free_transfers, LIMITS, SIZES,
                      club_limit=3, bench_weight=0.0, end_value_per_transfer=0.0, **kwargs)


@pytest.mark.parametrize("free_transfers", [0, 1, 2])
def test_one_week_matches_the_transfer_search(players, free_transfers):
    players = players.assign(xp_w1=players["projected_points"])
    search = search_transfers(make_squad(players, FULL_SQUAD, captain_id=4), players,
                              bank=1.0, limits=LIMITS, club_limit=3)
    expected = plan_transfers(search, free_transfers)
    best_net = expected["options"][expected["recommended"]]["net"]
    plan = _plan(players, ["xp_w1"], free_transfers)
    assert plan["gain"] == pytest.approx(best_net)


def _blank_next_week(players):
    """Week 1: as normal, plus a modest upgrade available (Fwd A -> Striker).
    Week 2: two of the squad's starting defenders blank (0 points) - fixing
    both needs two transfers."""
    extra = pd.DataFrame([
        {"id": 30, "web_name": "Striker", "full_name": "Striker", "team": "Wolves", "position": "FWD",
         "now_cost": 5.5, "projected_points": 4.0, "next_3_avg_difficulty": 3.0, "status": "a"},
        {"id": 31, "web_name": "NewDefA", "full_name": "NewDefA", "team": "Burnley", "position": "DEF",
         "now_cost": 4.5, "projected_points": 4.0, "next_3_avg_difficulty": 3.0, "status": "a"},
        {"id": 32, "web_name": "NewDefB", "full_name": "NewDefB", "team": "Burnley", "position": "DEF",
         "now_cost": 4.5, "projected_points": 4.0, "next_3_avg_difficulty": 3.0, "status": "a"},
    ])
    players = pd.concat([players, extra], ignore_index=True)
    # Take the usual big upgrades off the market, so the only question is
    # "roll, or spend the transfer on a small week-1 upgrade?".
    players.loc[players["web_name"].isin(["Saka", "DefF", "Saliba"]), "status"] = "i"
    players["xp_w1"] = players["projected_points"]
    players["xp_w2"] = players["projected_points"]
    # The new defenders only matter in week 2 (in week 1 they're no better than what's owned).
    players.loc[players["id"].isin([31, 32]), "xp_w1"] = 0.0
    # Week 2: DefA and DefB (starters) have no match.
    players.loc[players["web_name"].isin(["DefA", "DefB"]), "xp_w2"] = 0.0
    # Week 1: all five defenders are worth starting, so selling one early (to
    # pre-buy a week-2 replacement) costs points now. Without this, buying a
    # replacement early is exactly as good as rolling - a legitimate tactic,
    # but it wouldn't test the roll decision.
    players.loc[players["web_name"].isin(["DefC", "DefD", "DefE"]), "xp_w1"] = 5.0
    # Make the week-1 upgrade small: Striker only beats Fwd A by 1 point, in week 1 only.
    players.loc[players["id"] == 30, ["xp_w1", "xp_w2"]] = [4.0, 0.0]
    return players


def test_rolls_now_to_make_two_transfers_next_week(players):
    plan = _plan(_blank_next_week(players), ["xp_w1", "xp_w2"], free_transfers=1, bank=2.0)
    week1, week2 = plan["weeks"]
    assert week1["transfers"] == []                       # roll
    assert len(week2["transfers"]) == 2                   # both blank defenders replaced...
    assert week2["hits"] == 0                             # ...free, thanks to the rolled transfer
    assert week2["free_transfers"] == 2


def test_forcing_a_number_of_transfers_now(players):
    plan = _plan(_blank_next_week(players), ["xp_w1", "xp_w2"], free_transfers=1, bank=2.0,
                 transfers_now=1)
    assert len(plan["weeks"][0]["transfers"]) == 1
    rolled = _plan(_blank_next_week(players), ["xp_w1", "xp_w2"], free_transfers=1, bank=2.0)
    assert rolled["gain"] > plan["gain"]                  # rolling was better


def test_rules_hold_every_week(players):
    plan = _plan(_blank_next_week(players), ["xp_w1", "xp_w2"], free_transfers=2, bank=2.0)
    for week in plan["weeks"]:
        assert len(week["squad"]) == 15
        assert week["squad_value"] <= plan["budget"] + 1e-6
        assert week["club_counts"].max() <= 3
        assert week["free_transfers"] <= 5


def test_free_transfers_never_exceed_five(players):
    players = players.assign(xp_w1=players["projected_points"], xp_w2=players["projected_points"])
    plan = _plan(players, ["xp_w1", "xp_w2"], free_transfers=5, transfers_now=0)
    assert plan["weeks"][1]["free_transfers"] == 5       # 5 + 1 rolled, capped at 5


def test_advice_wording():
    from src.planner import advice
    week = lambda ft, hits=0: {"free_transfers": ft, "hits": hits, "transfers": []}  # noqa: E731
    roll = {"transfers_now": 0, "gain": 9.0, "plan": {"weeks": [week(1), week(2), week(1)]}}
    one = {"transfers_now": 1, "gain": 11.0, "plan": {"weeks": [week(1), week(1), week(1)]}}
    text = advice({"gameweeks": [9, 10, 11], "options": [roll, one], "best": one})
    assert text == "Make 1 transfer now. Worth +2.0 pts over GW9-11 compared with rolling."
    text = advice({"gameweeks": [9, 10, 11], "options": [roll, one], "best": {**roll, "gain": 12.0}})
    assert text.startswith("Roll - you'll have 2 free transfers next week. Worth +1.0 pts")
