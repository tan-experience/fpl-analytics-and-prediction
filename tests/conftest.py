"""
conftest.py
-----------
Shared test data. pytest automatically loads this file and makes its
"fixtures" available to every test - a test just names a fixture as a
parameter (e.g. `def test_something(players):`) and pytest passes it in.

Beginner notes:
- Tests never call the real FPL API. They use small hand-made tables
  instead, so they run in about a second, work offline, and give the same
  answer every time (real data changes every week).
- The players below are loosely based on real ones, but their numbers are
  made up to set up specific situations (an injured starter, two players
  called Palmer, a name with an accent, etc.).
"""

import pandas as pd
import pytest

# One row per player, with the columns our code reads from the projection
# table. Columns: id, display name, full name, team, position, price,
# projected points, avg difficulty of next 3 fixtures, status ('a' = available).
_PLAYERS = [
    (1, "Palmer", "Cole Palmer", "Chelsea", "MID", 9.7, 0.0, 3.0, "i"),  # injured
    (2, "Saka", "Bukayo Saka", "Arsenal", "MID", 9.5, 6.0, 2.0, "a"),
    (3, "Mbeumo", "Bryan Mbeumo", "Man Utd", "MID", 7.9, 5.0, 2.0, "a"),
    (4, "Haaland", "Erling Haaland", "Man City", "FWD", 15.0, 8.0, 2.5, "a"),
    (5, "Raya", "David Raya Martín", "Arsenal", "GKP", 5.5, 4.0, 2.0, "a"),
    (6, "B.Fernandes", "Bruno Borges Fernandes", "Man Utd", "MID", 11.9, 5.0, 2.0, "a"),
    (7, "Fernandes", "Mateus Fernandes", "Spurs", "MID", 5.7, 3.0, 3.0, "a"),
    (8, "João Pedro", "João Pedro Junqueira de Jesus", "Chelsea", "FWD", 7.7, 2.0, 3.0, "a"),
    (9, "Palmer", "Carl Palmer", "Ipswich", "GKP", 4.0, 1.0, 3.0, "a"),  # a second Palmer
    (10, "Gibbs-White", "Morgan Gibbs-White", "Nott'm Forest", "MID", 8.0, 4.0, 3.0, "a"),
]


@pytest.fixture
def players() -> pd.DataFrame:
    """A small stand-in for the projections table built from the FPL API."""
    return pd.DataFrame(_PLAYERS, columns=[
        "id", "web_name", "full_name", "team", "position", "now_cost",
        "projected_points", "next_3_avg_difficulty", "status",
    ])


def make_squad(players: pd.DataFrame, starter_ids: list, captain_id: int = None) -> pd.DataFrame:
    """
    Builds a squad table in the same shape team.get_squad_projection()
    returns, from the given player IDs (all starting).
    """
    rows = []
    for pid in starter_ids:
        p = players.set_index("id").loc[pid]
        multiplier = 2 if pid == captain_id else 1
        rows.append({
            "id": pid,
            "web_name": p["web_name"],
            "team": p["team"],
            "position": p["position"],
            "now_cost": p["now_cost"],
            "is_starting": True,
            "is_captain": pid == captain_id,
            "is_vice_captain": False,
            "multiplier": multiplier,
            "projected_points": p["projected_points"],
            "effective_points": p["projected_points"] * multiplier,
        })
    return pd.DataFrame(rows)
