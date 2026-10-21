"""
Tests for the free hit team (src/free_hit.py).

The key test compares the solver against BRUTE FORCE: on small made-up
player pools, try every possible legal squad (a few hundred), and check the
solver finds exactly the best one. If that holds across many random pools,
budgets and club mixes, the solver's rules are set up correctly.
"""

import random
from itertools import combinations, product

import pandas as pd
import pytest

from src.free_hit import best_squad
from src.lineup import best_total

LIMITS = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}
SIZES = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}


def _pool(seed: int, counts=None) -> pd.DataFrame:
    """A random pool: a few more players per position than a squad needs."""
    rng = random.Random(seed)
    counts = counts or {"GKP": 3, "DEF": 6, "MID": 6, "FWD": 4}
    rows, pid = [], 1
    for pos, n in counts.items():
        for _ in range(n):
            rows.append({"id": pid, "web_name": f"{pos}{pid}", "position": pos,
                         "team": rng.choice(["A", "B", "C", "D", "E"]),
                         "now_cost": round(rng.uniform(4.0, 12.0), 1),
                         "projected_points": round(rng.uniform(0.0, 9.0), 2), "status": "a"})
            pid += 1
    return pd.DataFrame(rows)


def _brute_force(pool: pd.DataFrame, budget: float, club_limit: int) -> float:
    """The best possible XI + captain total, by trying every legal squad."""
    by_pos = {pos: pool[pool["position"] == pos].to_dict("records") for pos in SIZES}
    best = None
    for picks in product(*(combinations(by_pos[pos], SIZES[pos]) for pos in SIZES)):
        squad = [p for group in picks for p in group]
        if sum(p["now_cost"] for p in squad) > budget + 1e-9:
            continue
        clubs = pd.Series([p["team"] for p in squad]).value_counts()
        if clubs.max() > club_limit:
            continue
        points = {pos: [p["projected_points"] for p in squad if p["position"] == pos] for pos in SIZES}
        total = best_total(points, LIMITS)
        best = total if best is None else max(best, total)
    return best


@pytest.mark.parametrize("seed", range(8))
def test_solver_matches_brute_force(seed):
    pool = _pool(seed)
    rng = random.Random(seed + 100)
    budget = round(rng.uniform(95.0, 125.0), 1)
    club_limit = rng.choice([3, 4])
    expected = _brute_force(pool, budget, club_limit)
    result = best_squad(pool, budget, LIMITS, SIZES, club_limit, bench_weight=0.0)
    if expected is None:
        assert result is None  # no legal squad fits the budget
    else:
        assert result["total"] == pytest.approx(expected, abs=1e-6)


def test_squad_obeys_every_rule():
    pool = _pool(42)
    result = best_squad(pool, 110.0, LIMITS, SIZES, club_limit=3)
    squad = result["squad"]
    assert squad["position"].value_counts().to_dict() == SIZES
    assert squad["now_cost"].sum() <= 110.0 + 1e-9
    assert squad["team"].value_counts().max() <= 3
    xi = squad[squad["starting"]]
    assert len(xi) == 11
    assert (xi["position"] == "GKP").sum() == 1
    assert squad["captain"].sum() == 1
    assert squad.loc[squad["captain"], "starting"].all()
    # The captain is the best starter (his points count twice).
    assert squad.loc[squad["captain"], "projected_points"].iloc[0] == xi["projected_points"].max()


def test_unavailable_players_are_never_picked():
    pool = _pool(7)
    best_id = pool.loc[pool["projected_points"].idxmax(), "id"]
    pool.loc[pool["id"] == best_id, "status"] = "i"  # injured
    # (Club limit relaxed: this small pool has no legal squad at 3 per club once
    # a player is removed - and this test is about injuries, not clubs.)
    result = best_squad(pool, 200.0, LIMITS, SIZES, club_limit=15)
    assert best_id not in set(result["squad"]["id"])


def test_impossible_budget_returns_none():
    assert best_squad(_pool(1), 20.0, LIMITS, SIZES, club_limit=3) is None


def test_squad_is_ordered_like_a_team_sheet():
    squad = best_squad(_pool(42), 110.0, LIMITS, SIZES, club_limit=3)["squad"]
    starters, bench = squad[squad["starting"]], squad[~squad["starting"]]
    assert list(squad["starting"]) == [True] * 11 + [False] * 4      # starters first
    assert starters["position"].iloc[0] == "GKP"                     # then by position
    assert bench["position"].iloc[0] == "GKP"                        # sub keeper first on the bench
