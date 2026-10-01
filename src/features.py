"""
features.py
------------
Turns the raw JSON from fetch.py into a single clean table (a pandas
DataFrame) of players, with the signals we need to project points:

- form: FPL's own rolling recent-form score
- chance_of_playing_next_round: 0-100, or None if no injury doubt
- expected_goal_involvements_per_90: underlying quality (xG + xA per 90 mins)
- next_fixture_difficulty: how hard their next match is (1=easiest, 5=hardest)

Beginner notes:
- A pandas DataFrame is like a spreadsheet in Python - rows and columns,
  with helpful tools for filtering/sorting/computing across them.
- "element" is FPL's internal name for "player" - you'll see it a lot in
  the raw API data.
"""

import pandas as pd

from src import fetch


def _upcoming_fixtures_for_team(team_id: int, fixtures: list) -> list:
    """
    All of a team's not-yet-played fixtures, in chronological order.
    Fixtures aren't guaranteed to arrive sorted; some also have event=None
    (not yet scheduled, e.g. postponed) - those get pushed to the end.
    """
    upcoming = [
        f for f in fixtures
        if not f["finished"] and (f["team_h"] == team_id or f["team_a"] == team_id)
    ]
    upcoming.sort(key=lambda f: (f["event"] is None, f["event"]))
    return upcoming


def _fixture_difficulty_for_team(team_id: int, fixture: dict) -> int:
    """Difficulty (1-5) of one fixture, from the given team's perspective."""
    if fixture["team_h"] == team_id:
        return fixture["team_h_difficulty"]
    return fixture["team_a_difficulty"]


def _next_fixture_difficulty(team_id: int, fixtures: list):
    """
    A team's single next fixture difficulty (1-5, higher = harder).
    Returns None if no upcoming fixture is found (e.g. end of season).
    """
    upcoming = _upcoming_fixtures_for_team(team_id, fixtures)
    if not upcoming:
        return None
    return _fixture_difficulty_for_team(team_id, upcoming[0])


def _next_n_fixtures_avg_difficulty(team_id: int, fixtures: list, n: int = 3):
    """
    Average difficulty across a team's next N fixtures - this is what
    catches a player who looks fine right now but has a brutal run coming
    up (or vice versa: an unfashionable player about to face three weak
    defenses in a row).

    Returns None if there are no upcoming fixtures at all.
    """
    upcoming = _upcoming_fixtures_for_team(team_id, fixtures)[:n]
    if not upcoming:
        return None
    difficulties = [_fixture_difficulty_for_team(team_id, f) for f in upcoming]
    return sum(difficulties) / len(difficulties)


def build_player_features() -> pd.DataFrame:
    """
    Returns one row per player, with the raw stats plus derived features
    needed for projection.
    """
    bootstrap = fetch.get_bootstrap_static()
    fixtures = fetch.get_fixtures()

    teams_by_id = {t["id"]: t["name"] for t in bootstrap["teams"]}
    positions_by_id = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}

    rows = []
    for p in bootstrap["elements"]:
        rows.append({
            "id": p["id"],
            "web_name": p["web_name"],
            "team": teams_by_id[p["team"]],
            "team_id": p["team"],
            "position": positions_by_id[p["element_type"]],
            "now_cost": p["now_cost"] / 10,  # FPL stores price *10, e.g. 95 -> 9.5
            "form": float(p["form"]),
            "points_per_game": float(p["points_per_game"]),
            "total_points": p["total_points"],
            "minutes": p["minutes"],
            "chance_of_playing_next_round": p["chance_of_playing_next_round"],
            "expected_goal_involvements_per_90": float(p["expected_goal_involvements_per_90"]),
            "status": p["status"],  # 'a' = available, 'i' = injured, 'u' = unavailable, etc.
        })

    df = pd.DataFrame(rows)

    # Add fixture difficulty per player, based on their team: both the very
    # next match (used for the single-gameweek projection in models.py) and
    # the average over the next 3 (used for spotting a tough/easy run when
    # considering transfers).
    df["next_fixture_difficulty"] = df["team_id"].apply(
        lambda tid: _next_fixture_difficulty(tid, fixtures)
    )
    df["next_3_avg_difficulty"] = df["team_id"].apply(
        lambda tid: _next_n_fixtures_avg_difficulty(tid, fixtures, n=3)
    )

    return df


if __name__ == "__main__":
    # Manual test: run `python -m src.features` from the project root.
    df = build_player_features()
    print(f"Built feature table for {len(df)} players.\n")
    print("Top 10 by form:")
    print(
        df.sort_values("form", ascending=False)
        .head(10)[["web_name", "team", "position", "form", "next_fixture_difficulty"]]
        .to_string(index=False)
    )
