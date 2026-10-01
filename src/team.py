"""
team.py
-------
Given any FPL team ID, pulls that manager's actual 15-player squad and joins
it with our projection model, so you can see projected points for a real
squad - yours or anyone else's.

Beginner notes:
- The FPL API's "picks" endpoint tells us WHICH 15 players are in a squad,
  who's captain, and who's on the bench - but not their stats. We already
  have stats/projections from features.py and models.py, so this file's
  job is just to join the two together.
- "multiplier" is FPL's own field: 0 = benched, 1 = starting normally,
  2 = captain (doubles points), 3 = triple captain (if that chip is active).
"""

import pandas as pd

from src import fetch
from src.features import build_player_features
from src.models import project_gameweek_points


def _target_gameweek(bootstrap: dict) -> int:
    """
    Figures out which gameweek to pull picks for.

    FPL's 'is_next' gameweek has no picks data yet - that squad doesn't lock
    in until its deadline passes, so the picks endpoint 404s for it. We prefer
    'is_current' - the gameweek whose picks actually exist - and only fall
    back to 'is_next' if there's no current gameweek at all (e.g. the season
    hasn't started yet). The forward-looking part of the projection comes
    from fixture-difficulty features, which look ahead independently of which
    gameweek the picks were pulled from.
    """
    events = bootstrap["events"]

    current = next((e for e in events if e["is_current"]), None)
    if current:
        return current["id"]

    upcoming = next((e for e in events if e["is_next"]), None)
    if upcoming:
        return upcoming["id"]

    raise ValueError("Could not determine a target gameweek from the FPL API data.")


def get_squad_projection(team_id: int, gameweek: int = None) -> pd.DataFrame:
    """
    Returns one row per player in the given team's squad (15 rows), with
    their projected points and whether they're starting/benched/captain.

    If `gameweek` isn't given, we use the current (or next) gameweek.

    Note: this reflects the squad as FPL has it recorded for that gameweek.
    If you're about to make transfers before the next deadline, re-run this
    after making them to see the updated projection.
    """
    bootstrap = fetch.get_bootstrap_static()
    if gameweek is None:
        gameweek = _target_gameweek(bootstrap)

    picks_data = fetch.get_entry_picks(team_id, gameweek)
    picks = picks_data["picks"]

    projections = project_gameweek_points(build_player_features())
    projections_by_id = projections.set_index("id")

    rows = []
    for pick in picks:
        player = projections_by_id.loc[pick["element"]]
        rows.append({
            "id": pick["element"],
            "web_name": player["web_name"],
            "team": player["team"],
            "position": player["position"],
            "now_cost": player["now_cost"],
            "is_starting": pick["multiplier"] > 0,
            "is_captain": pick["is_captain"],
            "is_vice_captain": pick["is_vice_captain"],
            "multiplier": pick["multiplier"],
            "projected_points": round(player["projected_points"], 2),
            "effective_points": round(player["projected_points"] * pick["multiplier"], 2),
        })

    squad_df = pd.DataFrame(rows)
    # Starting XI first (sorted by effective points), bench after.
    squad_df = squad_df.sort_values(
        by=["is_starting", "effective_points"], ascending=[False, False]
    ).reset_index(drop=True)

    return squad_df, gameweek


if __name__ == "__main__":
    # Manual test: run `python -m src.team` from the project root.
    # Change TEAM_ID below to project any manager's squad.
    TEAM_ID = 1524385

    squad_df, gameweek = get_squad_projection(TEAM_ID)
    starting_total = squad_df.loc[squad_df["is_starting"], "effective_points"].sum()

    print(f"Squad projection for team {TEAM_ID}, Gameweek {gameweek}:\n")
    print(squad_df.to_string(index=False))
    print(f"\nProjected starting XI total: {starting_total:.1f} points")
