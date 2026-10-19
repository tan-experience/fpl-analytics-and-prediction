"""
projections.py
--------------
The single place the CLI, transfer suggestions and web app get player
projections from.

get_projections() returns one row per player with:
- who they are: id, web_name, full_name, team, position, now_cost, status...
  (from features.py)
- projected_points: expected FPL points for the next deadline's gameweek
  (from expected_points.py - all scoring parts added up)
- the breakdown: xp_appearance, xp_clean_sheet_and_conceded,
  xp_defensive_contribution, xp_goals_and_assists, xp_bonus, xp_saves
- gameweek, and matches (0 = no match that week, 2 = a double gameweek)

Beginner note - caching: working out projections re-fits the team model,
which takes a moment, and the web app asks for projections several times
per page. So the result is kept in memory for CACHE_SECONDS and reused.
FPL data only refreshes hourly anyway (see fetch.py).
"""

import time

import pandas as pd

from src.expected_points import project_next_gameweek
from src.features import build_player_features

CACHE_SECONDS = 600  # 10 minutes

_cache = {}  # gameweek -> (time computed, projections table)


def get_projections(gameweek: int = None) -> pd.DataFrame:
    """Player info + expected points for the next deadline's gameweek (or the given one)."""
    cached = _cache.get(gameweek)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1].copy()  # a copy, so callers can't accidentally change the cached one

    features = build_player_features()
    expected = project_next_gameweek(gameweek)
    projections = features.merge(expected, on="id", how="inner")
    projections["projected_points"] = projections["xp_total"]

    _cache[gameweek] = (time.time(), projections)
    return projections.copy()


if __name__ == "__main__":
    # Manual check: run `python -m src.projections` from the project root.
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    p = get_projections()
    gw = int(p["gameweek"].iloc[0])
    print(f"Top 15 projected players, Gameweek {gw}:\n")
    cols = ["web_name", "team", "position", "now_cost", "matches", "xp_appearance",
            "xp_clean_sheet_and_conceded", "xp_defensive_contribution",
            "xp_goals_and_assists", "xp_bonus", "xp_saves", "projected_points"]
    print(p.nlargest(15, "projected_points")[cols].round(2).to_string(index=False))
