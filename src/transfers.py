"""
transfers.py
------------
Two things live here:

1. simulate_transfer() - "what if I swapped player A for player B?" Checks
   the swap is legal (same position, affordable, max 3 per club) and
   compares your BEST starting XI before and after - formation, captain
   and all - BEFORE you make the real transfer on the FPL site. Judging by
   best XI matters: a new signing might start ahead of someone else and
   change your formation, rather than simply taking the old player's slot.

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
from src.lineup import best_xi, formation_options, squad_limits
from src.projections import get_projections
from src.team import get_squad_projection

# How tough a next-3-gameweek average difficulty has to be before we flag it.
# FPL difficulty runs 1 (easiest) to 5 (hardest); 4+ is a genuinely hard run.
TOUGH_RUN_THRESHOLD = 4.0

# How fixture ease factors into ranking replacement candidates - same idea
# as models.py's fixture weight, reused here for consistency.
FIXTURE_WEIGHT = 0.3

# Max players from one club. None = read FPL's own rule from the API
# (it's 3); tests set a number so they don't need the API.
CLUB_LIMIT = None


def _get_bank(team_id: int) -> float:
    """Your remaining budget in the bank, in millions (e.g. 2.3 = £2.3m)."""
    entry = fetch.get_entry(team_id)
    return entry["last_deadline_bank"] / 10


def simulate_transfer(team_id: int, out_player_id: int, in_player_id: int, gameweek: int = None) -> dict:
    """
    Simulates swapping out_player_id for in_player_id in the given team's
    squad. Raises ValueError if the swap isn't legal (wrong position, not
    enough budget, a 4th player from one club, player not in your squad...).

    Returns a dict comparing your best XI before and after:
      before, after         best_xi() results (formation, xi, bench, captain, total)
      old_starting_total,   best XI projected points (captain included)
      new_starting_total
      projected_gain        new minus old
      joins_xi, leaves_xi   names of players who start after but not before, and vice versa
      formations_after      every formation's total after the transfer
      cost_diff, remaining_bank
    """
    squad_df, picks_gw = get_squad_projection(team_id, gameweek)
    projections = get_projections()
    proj_by_id = projections.set_index("id")

    def _name(player_id: int) -> str:
        """A player's display name for error messages, falling back to the ID
        only if the player doesn't exist at all."""
        if player_id in proj_by_id.index:
            return proj_by_id.loc[player_id, "web_name"]
        return f"Player id {player_id}"

    if out_player_id not in squad_df["id"].values:
        raise ValueError(f"{_name(out_player_id)} isn't in this squad.")
    if in_player_id in squad_df["id"].values:
        raise ValueError(f"{_name(in_player_id)} is already in this squad.")
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

    remaining = squad_df[squad_df["id"] != out_player_id]
    club_limit = fetch.get_bootstrap_static()["game_config"]["rules"]["squad_team_limit"]         if CLUB_LIMIT is None else CLUB_LIMIT
    if (remaining["team"] == in_row["team"]).sum() >= club_limit:
        raise ValueError(
            f"{in_row['web_name']} would be your {club_limit + 1}th {in_row['team']} player - "
            f"FPL allows at most {club_limit} from one club."
        )

    bank = _get_bank(team_id)
    cost_diff = round(in_row["now_cost"] - out_row["now_cost"], 1)
    if cost_diff > bank:
        raise ValueError(
            f"Not enough budget: this swap costs an extra £{cost_diff}m, "
            f"but you only have £{bank}m in the bank."
        )

    new_row = {col: in_row[col] for col in ("web_name", "team", "position", "now_cost", "projected_points")}
    new_squad_df = pd.concat([remaining, pd.DataFrame([{"id": in_player_id, **new_row}])],
                             ignore_index=True)

    limits = squad_limits()
    before = best_xi(squad_df, limits)
    after = best_xi(new_squad_df, limits)
    names = {**dict(zip(squad_df["id"], squad_df["web_name"])), in_player_id: in_row["web_name"]}

    return {
        "picks_gameweek": picks_gw,
        "old_squad": squad_df,
        "new_squad": new_squad_df,
        "before": before,
        "after": after,
        "old_starting_total": round(before["total"], 2),
        "new_starting_total": round(after["total"], 2),
        "projected_gain": round(after["total"] - before["total"], 2),
        "joins_xi": [names[i] for i in after["xi"]["id"] if i not in set(before["xi"]["id"])],
        "leaves_xi": [names[i] for i in before["xi"]["id"] if i not in set(after["xi"]["id"])],
        "formations_after": formation_options(new_squad_df, limits),
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

    projections = get_projections()
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
