"""
transfers.py
------------
Two things live here:

1. simulate_transfer() - "what if I swapped player A for player B?" Checks
   the swap is legal (same position, affordable) and shows the projected
   points impact BEFORE you make the real transfer on the FPL site.

2. suggest_transfers() - scans your current starting XI for players worth
   considering transferring out: ones NOT EXPECTED TO PLAY (projected 0 -
   injured, suspended, etc.), or ones both UNDERPERFORMING (below the
   average projection for their position in your squad) AND facing a
   TOUGH RUN (hard fixtures over the next 3 gameweeks, not just the next
   one) - then finds an affordable, better-positioned replacement.

Why both: the suggestion engine is a starting point, not a verdict - it
won't know about a player's penalty duties changing, a new signing hogging
minutes, etc. simulate_transfer() lets you sanity-check ANY swap you're
considering, whether it came from the suggestions or your own judgement.

Important simplification: FPL's actual "selling price" has special profit
rules (you don't always get full value back on a price-risen player). This
treats your sell price as equal to the player's current price, which is
close enough for comparing options but not exact to the pound.
"""

import pandas as pd

from src import fetch
from src.features import build_player_features
from src.models import project_gameweek_points
from src.team import get_squad_projection

# How tough a next-3-gameweek average difficulty has to be before we flag it.
# FPL difficulty runs 1 (easiest) to 5 (hardest); 4+ is a genuinely hard run.
TOUGH_RUN_THRESHOLD = 4.0

# How fixture ease factors into ranking replacement candidates - same idea
# as models.py's fixture weight, reused here for consistency.
FIXTURE_WEIGHT = 0.3


def _get_bank(team_id: int) -> float:
    """Your remaining budget in the bank, in millions (e.g. 2.3 = £2.3m)."""
    entry = fetch.get_entry(team_id)
    return entry["last_deadline_bank"] / 10


def simulate_transfer(team_id: int, out_player_id: int, in_player_id: int, gameweek: int = None) -> dict:
    """
    Simulates swapping out_player_id for in_player_id in the given team's
    squad. Raises ValueError if the swap isn't legal (wrong position, not
    enough budget, player not actually in your squad, etc).

    Returns a dict with the old/new squads and the projected points impact.
    """
    squad_df, picks_gw = get_squad_projection(team_id, gameweek)
    projections = project_gameweek_points(build_player_features())
    proj_by_id = projections.set_index("id")

    if out_player_id not in squad_df["id"].values:
        raise ValueError(f"Player id {out_player_id} isn't in this squad.")
    if in_player_id in squad_df["id"].values:
        raise ValueError(f"Player id {in_player_id} is already in this squad.")
    if in_player_id not in proj_by_id.index:
        raise ValueError(f"Player id {in_player_id} not found.")

    out_row = squad_df.loc[squad_df["id"] == out_player_id].iloc[0]
    in_row = proj_by_id.loc[in_player_id]

    if out_row["position"] != in_row["position"]:
        raise ValueError(
            f"Position mismatch: {out_row['web_name']} is {out_row['position']}, "
            f"{in_row['web_name']} is {in_row['position']}. A simple swap needs "
            f"the same position (otherwise your formation becomes illegal)."
        )

    bank = _get_bank(team_id)
    cost_diff = round(in_row["now_cost"] - out_row["now_cost"], 1)
    if cost_diff > bank:
        raise ValueError(
            f"Not enough budget: this swap costs an extra £{cost_diff}m, "
            f"but you only have £{bank}m in the bank."
        )

    # Build the new squad: same bench/captaincy slot as the player going out.
    new_row = {
        "id": in_player_id,
        "web_name": in_row["web_name"],
        "team": in_row["team"],
        "position": in_row["position"],
        "now_cost": in_row["now_cost"],
        "is_starting": out_row["is_starting"],
        "is_captain": out_row["is_captain"],
        "is_vice_captain": out_row["is_vice_captain"],
        "multiplier": out_row["multiplier"],
        "projected_points": round(in_row["projected_points"], 2),
        "effective_points": round(in_row["projected_points"] * out_row["multiplier"], 2),
    }
    if out_row["is_captain"]:
        # Flag rather than silently assume - the model doesn't know if the
        # incoming player is a sensible captaincy choice.
        new_row["_note"] = "Was captain - review whether this new player should keep the armband."

    new_squad_df = squad_df[squad_df["id"] != out_player_id].copy()
    new_squad_df = pd.concat([new_squad_df, pd.DataFrame([new_row])], ignore_index=True)

    old_total = squad_df.loc[squad_df["is_starting"], "effective_points"].sum()
    new_total = new_squad_df.loc[new_squad_df["is_starting"], "effective_points"].sum()

    return {
        "picks_gameweek": picks_gw,
        "old_squad": squad_df,
        "new_squad": new_squad_df,
        "old_starting_total": round(old_total, 2),
        "new_starting_total": round(new_total, 2),
        "projected_gain": round(new_total - old_total, 2),
        "cost_diff": cost_diff,
        "remaining_bank": round(bank - cost_diff, 2),
    }


def suggest_transfers(team_id: int, gameweek: int = None, max_suggestions: int = 3) -> list:
    """
    Flags starting players worth considering transferring out: ones not
    expected to play, or ones both underperforming for their position AND
    facing a tough 3-gameweek run, then finds the best affordable same-position replacement.

    Returns a list of suggestion dicts, best first, each with the player ids
    so you can feed them straight into simulate_transfer() if you like one.
    """
    squad_df, picks_gw = get_squad_projection(team_id, gameweek)
    bank = _get_bank(team_id)

    projections = project_gameweek_points(build_player_features())
    proj_by_id = projections.set_index("id")

    squad_with_fixtures = squad_df.copy()
    squad_with_fixtures["next_3_avg_difficulty"] = squad_with_fixtures["id"].map(
        proj_by_id["next_3_avg_difficulty"]
    )

    starters = squad_with_fixtures[squad_with_fixtures["is_starting"]].copy()
    starters["position_avg_points"] = starters.groupby("position")["projected_points"].transform("mean")

    # Two separate reasons to flag a starter:
    # 1. Not expected to play at all (projection is 0 - injured, suspended,
    #    or ruled out). This trumps everything: a player who won't play is
    #    a problem no matter how easy their fixtures are.
    # 2. Underperforming for their position AND facing a tough run.
    not_playing = starters["projected_points"] <= 0
    weak_and_tough_run = (
        (starters["next_3_avg_difficulty"] >= TOUGH_RUN_THRESHOLD)
        & (starters["projected_points"] < starters["position_avg_points"])
    )
    flagged = starters[not_playing | weak_and_tough_run].copy()
    flagged["reason"] = "tough run + below position average"
    flagged.loc[not_playing, "reason"] = "not expected to play"

    squad_ids = set(squad_df["id"])
    suggestions = []

    for _, weak in flagged.iterrows():
        budget_ceiling = weak["now_cost"] + bank

        candidates = projections[
            (projections["position"] == weak["position"])
            & (~projections["id"].isin(squad_ids))
            & (projections["now_cost"] <= budget_ceiling)
            & (projections["status"] == "a")
        ].copy()
        if candidates.empty:
            continue

        # Rank candidates by projected points, discounted for a tough run of
        # their own - same logic as the weak player's own score, so it's an
        # apples-to-apples comparison.
        def _score(row):
            difficulty = row["next_3_avg_difficulty"] if pd.notna(row["next_3_avg_difficulty"]) else 3.0
            return row["projected_points"] - FIXTURE_WEIGHT * difficulty

        weak_difficulty = weak["next_3_avg_difficulty"] if pd.notna(weak["next_3_avg_difficulty"]) else 3.0
        weak_score = weak["projected_points"] - FIXTURE_WEIGHT * weak_difficulty

        candidates["upgrade_score"] = candidates.apply(_score, axis=1)
        candidates = candidates[candidates["upgrade_score"] > weak_score]
        if candidates.empty:
            continue

        best = candidates.sort_values("upgrade_score", ascending=False).iloc[0]

        suggestions.append({
            "reason": weak["reason"],
            "out_id": int(weak["id"]),
            "out_name": weak["web_name"],
            "out_projected_points": round(weak["projected_points"], 2),
            "out_next_3_difficulty": round(weak_difficulty, 1),
            "in_id": int(best["id"]),
            "in_name": best["web_name"],
            "in_projected_points": round(best["projected_points"], 2),
            "in_next_3_difficulty": round(best["next_3_avg_difficulty"], 1) if pd.notna(best["next_3_avg_difficulty"]) else None,
            "cost_diff": round(best["now_cost"] - weak["now_cost"], 1),
        })

    suggestions.sort(key=lambda s: s["in_projected_points"] - s["out_projected_points"], reverse=True)
    return suggestions[:max_suggestions]


if __name__ == "__main__":
    # Manual test: run `python -m src.transfers` from the project root.
    TEAM_ID = 895045  # example: overall FPL leader after GW5 - swap in your own ID

    print("Scanning your starting XI for transfer suggestions "
          "(not playing, or underperforming + tough next-3-gameweek run)...\n")
    suggestions = suggest_transfers(TEAM_ID)

    if not suggestions:
        print("Nothing flagged - your starters look fine on form and fixtures for now.")
    else:
        for i, s in enumerate(suggestions, start=1):
            print(f"{i}. OUT: {s['out_name']} "
                  f"(proj {s['out_projected_points']}, next-3 difficulty {s['out_next_3_difficulty']})")
            print(f"   IN:  {s['in_name']} "
                  f"(proj {s['in_projected_points']}, next-3 difficulty {s['in_next_3_difficulty']}, "
                  f"cost diff £{s['cost_diff']}m)")
            print(f"   -> simulate_transfer({TEAM_ID}, out_player_id={s['out_id']}, in_player_id={s['in_id']})\n")

    print("To test your OWN transfer idea (any two players, same position):")
    print(f"  from src.transfers import simulate_transfer")
    print(f"  result = simulate_transfer({TEAM_ID}, out_player_id=X, in_player_id=Y)")
    print(f"  print(f\"Projected gain: {{result['projected_gain']}} points, "
          f"£{{result['remaining_bank']}}m left in bank\")")
