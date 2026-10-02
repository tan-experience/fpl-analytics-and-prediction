"""
cli.py
------
The command-line front door to the project. Instead of opening Python and
calling functions by hand, you run one command from the project root:

    python -m src.cli --team 1524385
        -> your squad's projected points + top transfer suggestions

    python -m src.cli --team 1524385 --out Salah --in Palmer
        -> "what if" a specific transfer (names or player IDs both work)

Beginner notes:
- `argparse` is Python's built-in tool for reading command-line options
  like `--team 123`. It also gives you `--help` for free.
- This file contains almost no logic of its own - it just calls the
  functions in team.py and transfers.py and prints their results nicely.
  Keeping the "thinking" code separate from the "printing" code means a
  future Streamlit app can reuse the same functions without changes.
"""

import argparse
import sys

from src.features import build_player_features
from src.models import project_gameweek_points
from src.team import get_squad_projection
from src.transfers import simulate_transfer, suggest_transfers

# Columns to show in the squad table, and friendlier headings for them.
SQUAD_COLUMNS = {
    "web_name": "Player",
    "position": "Pos",
    "now_cost": "Price",
    "projected_points": "Proj",
    "effective_points": "Eff",
}


def _money(value: float) -> str:
    """Formats a price change as e.g. '+£0.5m' or '-£0.4m'."""
    return f"{'-' if value < 0 else '+'}£{abs(value):.1f}m"


def _resolve_player(value: str, projections, prefer_ids=None) -> int:
    """
    Turns what the user typed after --out / --in into a player ID.

    Accepts either a number (used as the ID directly) or a name like
    "Salah" (matched case-insensitively against FPL's short display name).
    If a name matches several players, we stop and list them, rather than
    guessing - picking the wrong player silently would be worse than asking.

    `prefer_ids` narrows the search first: for --out we pass your squad's
    IDs, since you can only sell someone you own. So "--out Palmer" picks
    YOUR Palmer even though FPL has two.
    """
    if value.isdigit():
        return int(value)

    if prefer_ids is not None:
        preferred = projections[projections["id"].isin(prefer_ids)]
        try:
            return _resolve_player(value, preferred)
        except ValueError:
            pass  # Not found in the preferred pool - fall back to everyone.

    matches = projections[projections["web_name"].str.lower() == value.lower()]
    if matches.empty:
        # No exact match - try "contains" so "Alexander" finds "Alexander-Arnold".
        matches = projections[projections["web_name"].str.lower().str.contains(value.lower(), regex=False)]

    if matches.empty:
        raise ValueError(f"No player found matching '{value}'.")
    if len(matches) > 1:
        options = "\n".join(
            f"  {row.id}: {row.web_name} ({row.position}, £{row.now_cost}m)"
            for row in matches.itertuples()
        )
        raise ValueError(f"'{value}' matches several players - use an ID instead:\n{options}")

    return int(matches.iloc[0]["id"])


def _format_squad(squad_df) -> str:
    """Prints the squad as a table, marking captain (C) and vice (V)."""
    table = squad_df.copy()
    table["web_name"] = table.apply(
        lambda r: r["web_name"] + (" (C)" if r["is_captain"] else " (V)" if r["is_vice_captain"] else ""),
        axis=1,
    )
    starters = table[table["is_starting"]][list(SQUAD_COLUMNS)].rename(columns=SQUAD_COLUMNS)
    bench = table[~table["is_starting"]][list(SQUAD_COLUMNS)].rename(columns=SQUAD_COLUMNS)
    return (
        "Starting XI:\n" + starters.to_string(index=False)
        + "\n\nBench:\n" + bench.to_string(index=False)
    )


def show_squad_and_suggestions(team_id: int) -> None:
    """Default mode: squad projection, then transfer suggestions."""
    squad_df, gameweek = get_squad_projection(team_id)
    total = squad_df.loc[squad_df["is_starting"], "effective_points"].sum()

    print(f"Team {team_id} - squad as locked in for Gameweek {gameweek}, "
          f"projected for the next fixture\n")
    print(_format_squad(squad_df))
    print(f"\nProjected starting XI total: {total:.1f} points")
    print("(Proj = player's projection, Eff = after captain/bench multiplier)\n")

    print("Transfer suggestions (starters not expected to play, or underperforming + tough run):")
    suggestions = suggest_transfers(team_id)
    if not suggestions:
        print("  Nothing flagged - your starters look fine on form and fixtures for now.")
        return

    for i, s in enumerate(suggestions, start=1):
        gain = s["in_projected_points"] - s["out_projected_points"]
        print(f"  {i}. {s['out_name']} -> {s['in_name']}  "
              f"(+{gain:.2f} pts, cost {_money(s['cost_diff'])}) - {s['reason']}")
        print(f"     Try it: python -m src.cli --team {team_id} --out {s['out_id']} --in {s['in_id']}")


def show_what_if(team_id: int, out_value: str, in_value: str) -> None:
    """What-if mode: simulate one specific transfer."""
    projections = project_gameweek_points(build_player_features())
    squad_df, _ = get_squad_projection(team_id)
    out_id = _resolve_player(out_value, projections, prefer_ids=set(squad_df["id"]))
    in_id = _resolve_player(in_value, projections)

    result = simulate_transfer(team_id, out_player_id=out_id, in_player_id=in_id)

    names = projections.set_index("id")["web_name"]
    print(f"What if: {names[out_id]} -> {names[in_id]}\n")
    print(f"  Starting XI projection: {result['old_starting_total']:.2f} -> "
          f"{result['new_starting_total']:.2f}  ({result['projected_gain']:+.2f} pts)")
    print(f"  Cost difference: {_money(result['cost_diff'])}, "
          f"leaving £{result['remaining_bank']}m in the bank")

    note = result["new_squad"].get("_note")
    if note is not None and note.notna().any():
        print(f"  Note: {note.dropna().iloc[0]}")

    print("\n  (Sell price assumed = current price; see DECISIONS.md.)")


def main(argv=None) -> int:
    # Windows terminals often default to an old text encoding that mangles
    # names like "Groß" and the £ sign. Forcing UTF-8 output fixes that.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="Project your FPL squad's points and test transfer ideas.",
    )
    parser.add_argument("--team", type=int, required=True,
                        help="Your FPL team ID (the number in your FPL points-page URL).")
    parser.add_argument("--out", dest="out_player",
                        help="Player to transfer out (name or ID). Use with --in.")
    # `in` is a reserved word in Python, so we store it under a different name.
    parser.add_argument("--in", dest="in_player",
                        help="Player to transfer in (name or ID). Use with --out.")
    args = parser.parse_args(argv)

    # --out and --in only make sense as a pair.
    if bool(args.out_player) != bool(args.in_player):
        parser.error("--out and --in must be used together.")

    try:
        if args.out_player:
            show_what_if(args.team, args.out_player, args.in_player)
        else:
            show_squad_and_suggestions(args.team)
    except ValueError as e:
        # Expected problems (unknown player, illegal swap, over budget) get a
        # clean one-line message instead of a scary Python traceback.
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
