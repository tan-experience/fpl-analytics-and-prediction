"""
free_hit.py
-----------
The best possible squad for ONE gameweek within your budget - what you'd
pick with FPL's Free Hit chip (a one-week squad that reverts afterwards).
Useful for deciding whether to play the chip this week, or save it for a
blank gameweek when many of your players don't have a match.

Run it from the project root:

    python -m src.free_hit 895045

How it works - "integer programming": choosing 15 players from ~670 has far
too many combinations to try them all, so we describe the problem to a
SOLVER (HiGHS, via the PuLP library), which finds the provably best answer.
For every player it decides three yes/no questions at once:
    in the squad?   starting?   captain?
...to maximise the starting XI's expected points, with the captain's
counted twice (plus a little weight on the bench, since a bench player
only scores if a starter doesn't play), subject to FPL's rules:
- exactly 2 GKP, 5 DEF, 5 MID, 3 FWD
- 11 starters in a legal formation (1 GKP, 3-5 DEF, 2-5 MID, 1-3 FWD)
- one captain, who must start
- at most 3 players from one club
- total cost within the budget
Injured, suspended and departed players are left out.

Tests check the solver against brute force (trying every possible squad)
on small pools, so the rules above are known to be set up correctly.
"""

import pandas as pd
import pulp

from src import fetch
from src.lineup import best_xi, squad_limits

POSITIONS = ["GKP", "DEF", "MID", "FWD"]
UNAVAILABLE = ("i", "s", "u", "n")

# How much a bench player's projected points count: a starter usually
# plays, so a bench player only scores occasionally (automatic subs).
BENCH_WEIGHT = 0.1


def squad_sizes() -> dict:
    """{position: players in a 15-man squad} from FPL's settings (2/5/5/3)."""
    return {p["singular_name_short"]: p["squad_select"]
            for p in fetch.get_bootstrap_static()["element_types"] if p["singular_name_short"] in POSITIONS}


def best_squad(players: pd.DataFrame, budget: float, limits: dict, sizes: dict,
               club_limit: int, bench_weight: float = BENCH_WEIGHT) -> dict:
    """
    The best legal 15 for one gameweek. `players` needs: id, web_name, team,
    position, now_cost, projected_points, status.

    Returns None if no legal squad fits the budget, otherwise:
      squad   the 15, with "starting" and "captain" columns (True/False)
      total   starting XI's projected points + captain's again (no bench weight)
      cost    the squad's total price
    """
    pool = players[~players["status"].isin(UNAVAILABLE)].reset_index(drop=True)
    ids = list(pool.index)
    points = pool["projected_points"].tolist()

    problem = pulp.LpProblem("free_hit", pulp.LpMaximize)
    in_squad = problem.add_variable_dict("squad", ids, cat="Binary")
    starts = problem.add_variable_dict("start", ids, cat="Binary")
    captain = problem.add_variable_dict("captain", ids, cat="Binary")

    # Objective: starters + captain again + a little for the bench.
    problem += pulp.lpSum(points[i] * (starts[i] + captain[i] + bench_weight * (in_squad[i] - starts[i]))
                          for i in ids)

    for pos in POSITIONS:
        members = [i for i in ids if pool.at[i, "position"] == pos]
        problem += pulp.lpSum(in_squad[i] for i in members) == sizes[pos]
        problem += pulp.lpSum(starts[i] for i in members) >= limits[pos][0]
        problem += pulp.lpSum(starts[i] for i in members) <= limits[pos][1]
    problem += pulp.lpSum(starts[i] for i in ids) == 11
    problem += pulp.lpSum(captain[i] for i in ids) == 1
    for i in ids:
        problem += starts[i] <= in_squad[i]
        problem += captain[i] <= starts[i]
    for club in pool["team"].unique():
        problem += pulp.lpSum(in_squad[i] for i in ids if pool.at[i, "team"] == club) <= club_limit
    problem += pulp.lpSum(pool.at[i, "now_cost"] * in_squad[i] for i in ids) <= budget

    result = problem.solve(pulp.HiGHS(msg=False))
    if result.status != pulp.LpSolveStatus.Optimal:
        return None  # e.g. no legal squad fits the budget

    chosen = [i for i in ids if in_squad[i].value() > 0.5]
    squad = pool.loc[chosen].copy()
    squad["starting"] = [starts[i].value() > 0.5 for i in chosen]
    squad["captain"] = [captain[i].value() > 0.5 for i in chosen]
    xi = squad[squad["starting"]]
    total = xi["projected_points"].sum() + squad.loc[squad["captain"], "projected_points"].sum()

    # Order like a team sheet: starters by position (best first), then the
    # bench with the sub goalkeeper first (FPL's bench rule).
    squad["_pos"] = squad["position"].map(POSITIONS.index)
    squad["_bench_order"] = (squad["position"] != "GKP").astype(int)
    squad = pd.concat([
        squad[squad["starting"]].sort_values(["_pos", "projected_points"], ascending=[True, False]),
        squad[~squad["starting"]].sort_values(["_bench_order", "projected_points"], ascending=[True, False]),
    ]).drop(columns=["_pos", "_bench_order"])
    return {"squad": squad.reset_index(drop=True), "total": float(total),
            "cost": float(squad["now_cost"].sum())}


def free_hit_for_team(team_id: int) -> dict:
    """
    The free hit squad for a real team's budget (current squad value + bank,
    at today's prices - FPL uses selling prices, which can be slightly lower),
    compared with the best XI from the team's current squad.
    """
    from src.projections import get_projections
    from src.team import get_squad_projection
    from src.transfers import _club_limit, _get_bank

    squad_df, _ = get_squad_projection(team_id)
    budget = round(squad_df["now_cost"].sum() + _get_bank(team_id), 1)
    limits = squad_limits()
    result = best_squad(get_projections(), budget, limits, squad_sizes(), _club_limit())
    current = best_xi(squad_df, limits)
    result.update({
        "budget": budget,
        "current_total": current["total"],
        "gain": result["total"] - current["total"],
        "formation": best_xi(result["squad"], limits)["formation"],
        "kept": sorted(set(result["squad"]["id"]) & set(squad_df["id"])),
    })
    return result


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    team_id = int(sys.argv[1]) if len(sys.argv) > 1 else 895045
    fh = free_hit_for_team(team_id)
    squad = fh["squad"]
    print(f"Free hit for team {team_id} - budget £{fh['budget']:.1f}m, squad costs £{fh['cost']:.1f}m")
    print(f"Best XI + captain: {fh['total']:.1f} pts vs your current best XI {fh['current_total']:.1f} "
          f"({fh['gain']:+.1f}); formation {fh['formation']}\n")
    for starting, label in ((True, "Starting XI"), (False, "Bench")):
        print(label + ":")
        part = squad[squad["starting"] == starting].sort_values(["position", "projected_points"],
                                                                 key=lambda c: c.map(POSITIONS.index)
                                                                 if c.name == "position" else -c)
        for row in part.itertuples():
            print(f"  {row.position} {row.web_name:15} {row.team:15} £{row.now_cost:4.1f}m  "
                  f"{row.projected_points:4.2f}{'  (C)' if row.captain else ''}")
