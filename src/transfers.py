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

2. search_transfers() / plan_transfers() / suggest_transfers() - search
   every legal single transfer and every pair of transfers, score each by
   how much it improves your BEST XI, and decide whether making a second
   transfer is worth FPL's -4 points "hit".

   Limitation: this looks at the NEXT GAMEWEEK only. A new player keeps
   scoring for weeks, so a one-week view undervalues transfers - hits
   especially. Multi-gameweek projections are on the roadmap.

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
from src.lineup import best_total, best_xi, formation_options, squad_limits
from src.projections import get_projections
from src.team import get_squad_projection

# FPL's cost of each transfer beyond your free ones.
HIT_COST = 4

# For pairs of transfers, how many of the best replacements to try for each
# player sold. Pairs are where a cheaper downgrade funds an upgrade
# elsewhere, so we look beyond the single best option per player.
CANDIDATES_PER_PLAYER = 10

# Player statuses that mean "won't play" - never suggested as replacements.
UNAVAILABLE = ("i", "s", "u", "n")

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


def _points_by_position(rows) -> dict:
    """{position: [projected points]} for best_total()."""
    by_pos = {}
    for row in rows:
        by_pos.setdefault(row["position"], []).append(row["projected_points"])
    return by_pos


def _clubs_ok(rows, club_limit: int) -> bool:
    """True if no club has more than club_limit players in these rows."""
    counts = {}
    for row in rows:
        counts[row["team"]] = counts.get(row["team"], 0) + 1
    return max(counts.values()) <= club_limit


def search_transfers(squad: pd.DataFrame, projections: pd.DataFrame, bank: float,
                     limits: dict, club_limit: int) -> dict:
    """
    Searches transfers for a squad, scoring each by how much it improves
    the best XI (formation and captain chosen each time).

    Returns:
      base_total  the best XI's projected points now
      singles     DataFrame, one row per player you could sell: their best
                  legal replacement and the gain (best first)
      best_pair   dict for the best combination of two transfers (or None)

    "Legal" = same position, affordable (with the bank - and for pairs, the
    money from both sales together), at most club_limit per club, and the
    incoming player isn't injured/suspended/gone.
    """
    cols = ["id", "web_name", "team", "position", "now_cost", "projected_points"]
    squad_rows = squad[cols].to_dict("records")
    base_total = best_total(_points_by_position(squad_rows), limits)
    owned = set(squad["id"])

    # Possible replacements per position, best projected first.
    pool = projections[~projections["id"].isin(owned) & ~projections["status"].isin(UNAVAILABLE)
                       & (projections["projected_points"] > 0)]
    pool_by_position = {
        pos: group.sort_values("projected_points", ascending=False)[cols].to_dict("records")
        for pos, group in pool.groupby("position")
    }

    def _total_after(outs, ins):
        """Best XI total after selling `outs` (ids) and buying `ins` (rows); None if illegal."""
        rows = [r for r in squad_rows if r["id"] not in outs] + list(ins)
        if not _clubs_ok(rows, club_limit):
            return None
        return best_total(_points_by_position(rows), limits)

    # ---- singles: for each player sold, the best legal replacement.
    # A better-projected replacement can never lower the best XI, so the
    # first legal one in the (best-first) pool is the best for that player.
    singles = []
    for out in squad_rows:
        for cand in pool_by_position.get(out["position"], []):
            if cand["now_cost"] - out["now_cost"] > bank + 1e-9:
                continue
            total = _total_after({out["id"]}, [cand])
            if total is None:
                continue
            singles.append({
                "out_id": out["id"], "out_name": out["web_name"],
                "out_projected_points": out["projected_points"],
                "in_id": cand["id"], "in_name": cand["web_name"],
                "in_projected_points": cand["projected_points"],
                "cost_diff": round(cand["now_cost"] - out["now_cost"], 1),
                "gain": total - base_total,
            })
            break
    singles = pd.DataFrame(singles, columns=[
        "out_id", "out_name", "out_projected_points", "in_id", "in_name",
        "in_projected_points", "cost_diff", "gain",
    ]).sort_values("gain", ascending=False, kind="stable").reset_index(drop=True)

    # ---- pairs: two players sold, two bought, with the budget shared.
    best_pair = None
    most_freed = max(r["now_cost"] for r in squad_rows)  # the most a 2nd sale could free up
    for i, out1 in enumerate(squad_rows):
        for out2 in squad_rows[i + 1:]:
            budget = bank + out1["now_cost"] + out2["now_cost"]
            cands1 = [c for c in pool_by_position.get(out1["position"], [])
                      if c["now_cost"] <= out1["now_cost"] + bank + most_freed][:CANDIDATES_PER_PLAYER]
            cands2 = [c for c in pool_by_position.get(out2["position"], [])
                      if c["now_cost"] <= out2["now_cost"] + bank + most_freed][:CANDIDATES_PER_PLAYER]
            for in1 in cands1:
                for in2 in cands2:
                    if in1["id"] == in2["id"] or in1["now_cost"] + in2["now_cost"] > budget + 1e-9:
                        continue
                    total = _total_after({out1["id"], out2["id"]}, [in1, in2])
                    if total is None:
                        continue
                    gain = total - base_total
                    if best_pair is None or gain > best_pair["gain"] + 1e-9:
                        best_pair = {"outs": [out1, out2], "ins": [in1, in2], "gain": gain}

    if best_pair:
        new_squad = squad[~squad["id"].isin([o["id"] for o in best_pair["outs"]])][cols]
        new_squad = pd.concat([new_squad, pd.DataFrame(best_pair["ins"])], ignore_index=True)
        best_pair = {
            "out_ids": [o["id"] for o in best_pair["outs"]],
            "out_names": [o["web_name"] for o in best_pair["outs"]],
            "in_ids": [c["id"] for c in best_pair["ins"]],
            "in_names": [c["web_name"] for c in best_pair["ins"]],
            "cost_diff": round(sum(c["now_cost"] for c in best_pair["ins"])
                               - sum(o["now_cost"] for o in best_pair["outs"]), 1),
            "gain": best_pair["gain"],
            "formation_after": best_xi(new_squad, limits)["formation"],
        }

    return {"base_total": base_total, "singles": singles, "best_pair": best_pair}


def plan_transfers(search: dict, free_transfers: int = 1) -> dict:
    """
    Compares three plans for this gameweek - no transfer, the best single
    transfer, the best pair - after FPL's -4 points for each transfer
    beyond your free ones. Recommends the plan with the highest net gain
    (on a tie, the one with fewer transfers).

    Returns: options {"none"/"single"/"pair": {gain, transfers, hit, net}},
             recommended, free_transfers, and hit_worth_it (True/False when
             the pair needs a hit the single doesn't; otherwise None).
    """
    def _option(gain, transfers):
        hit = HIT_COST * max(0, transfers - free_transfers)
        return {"gain": gain, "transfers": transfers, "hit": hit, "net": gain - hit}

    options = {"none": _option(0.0, 0)}
    if len(search["singles"]):
        options["single"] = _option(float(search["singles"]["gain"].iloc[0]), 1)
    if search["best_pair"]:
        options["pair"] = _option(search["best_pair"]["gain"], 2)

    recommended = "none"
    for name in ("single", "pair"):
        if name in options and options[name]["net"] > options[recommended]["net"] + 1e-9:
            recommended = name

    hit_worth_it = None
    if "pair" in options and "single" in options and options["pair"]["hit"] > options["single"]["hit"]:
        hit_worth_it = options["pair"]["net"] > options["single"]["net"] + 1e-9
    return {"options": options, "recommended": recommended, "hit_worth_it": hit_worth_it,
            "free_transfers": free_transfers}


def explain(row) -> str:
    """Plain-English reason for a single-transfer suggestion."""
    if row["out_projected_points"] <= 0:
        return f"{row['out_name']} isn't expected to play"
    return (f"{row['in_name']} projects {row['in_projected_points']:.1f} pts "
            f"vs {row['out_name']}'s {row['out_projected_points']:.1f}")


def transfer_search_for_team(team_id: int, gameweek: int = None) -> dict:
    """search_transfers() for a real team, using its squad and bank from the API."""
    squad_df, _ = get_squad_projection(team_id, gameweek)
    club_limit = (fetch.get_bootstrap_static()["game_config"]["rules"]["squad_team_limit"]
                  if CLUB_LIMIT is None else CLUB_LIMIT)
    return search_transfers(squad_df, get_projections(), _get_bank(team_id), squad_limits(), club_limit)


def suggestions_from_search(search: dict, max_suggestions: int = 3) -> list:
    """
    The best single transfers from a search_transfers() result, as dicts with
    out/in ids and names, projections, cost_diff, gain and a plain-English
    reason. Transfers that don't improve the best XI aren't included.
    """
    singles = search["singles"]
    singles = singles[singles["gain"] > 0.05].head(max_suggestions)
    return [{**row, "reason": explain(row)} for row in singles.to_dict("records")]


def suggest_transfers(team_id: int, gameweek: int = None, max_suggestions: int = 3) -> list:
    """The best single transfers for a team, ranked by how much they improve the best XI."""
    return suggestions_from_search(transfer_search_for_team(team_id, gameweek), max_suggestions)


if __name__ == "__main__":
    # Manual test: run `python -m src.transfers` from the project root.
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    TEAM_ID = 895045  # example: overall FPL leader after GW5 - swap in your own ID

    search = transfer_search_for_team(TEAM_ID)
    print(f"Best XI now: {search['base_total']:.1f} projected points\n")
    for i, s in enumerate(suggestions_from_search(search), start=1):
        print(f"{i}. {s['out_name']} -> {s['in_name']}  (+{s['gain']:.2f}, {s['reason']})")
    for free in (1, 2):
        plan = plan_transfers(search, free_transfers=free)
        print(f"\nWith {free} free transfer(s): recommended = {plan['recommended']}")
        for name, option in plan["options"].items():
            print(f"  {name:6}  gain {option['gain']:+.2f}  hit -{option['hit']}  net {option['net']:+.2f}")
