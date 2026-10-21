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


HORIZON = 3  # gameweeks ahead for get_horizon_projections()

_horizon_cache = {}  # weeks -> (time computed, table)


def get_horizon_projections(weeks: int = HORIZON) -> pd.DataFrame:
    """
    Expected points for each of the next `weeks` gameweeks, one row per
    player: the usual player info, xp_gw<N> and matches_gw<N> for each
    gameweek, and xp_total across them all. Cached like get_projections().

    Simplification: FPL's injury percentage only applies to the NEXT round,
    but we apply it to all of them - so a doubtful player is (cautiously)
    scaled down for every week, and an injured one counts as 0 throughout.
    """
    cached = _horizon_cache.get(weeks)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1].copy()

    from src import fetch
    events = fetch.get_bootstrap_static()["events"]
    next_gw = next(e["id"] for e in events if e["is_next"])
    valid = {e["id"] for e in events}
    gameweeks = [gw for gw in range(next_gw, next_gw + weeks) if gw in valid]

    table = build_player_features()
    for gw in gameweeks:
        week = project_next_gameweek(gw)[["id", "xp_total", "matches"]].rename(
            columns={"xp_total": f"xp_gw{gw}", "matches": f"matches_gw{gw}"})
        table = table.merge(week, on="id", how="inner")
    table["xp_total"] = table[[f"xp_gw{gw}" for gw in gameweeks]].sum(axis=1)
    table.attrs["gameweeks"] = gameweeks  # which weeks the columns cover

    _horizon_cache[weeks] = (time.time(), table)
    return table.copy()


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
