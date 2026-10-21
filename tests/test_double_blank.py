"""
Double and blank gameweeks, end to end through the live projection
(expected_points.project_next_gameweek), with a tiny made-up league:

  GW1 (played):  A v B, B v C, C v A
  GW2 (next):    A v B, C v A     -> A plays TWICE (double), B and C once
  GW3:           A v B            -> C doesn't play (blank)

Three identical midfielders, one per team, and three identical teams - so
any difference comes from the number of matches (and home/away).
"""

import pandas as pd
import pytest

import src.attacking_points as attacking_points
import src.defensive_points as defensive_points
from src import fetch
from src.expected_points import project_next_gameweek
from src.team_strength import TeamStrengths

TEAMS = [{"id": 1, "name": "A", "short_name": "AAA"}, {"id": 2, "name": "B", "short_name": "BBB"},
         {"id": 3, "name": "C", "short_name": "CCC"}]


def _fixture(fid, gw, home, away, played):
    return {"id": fid, "event": gw, "team_h": home, "team_a": away, "finished_provisional": played,
            "finished": played, "kickoff_time": f"2026-08-{10 + 7 * gw:02d}T15:00:00Z",
            "team_h_difficulty": 3, "team_a_difficulty": 3}


FIXTURES = [
    _fixture(1, 1, 1, 2, True), _fixture(2, 1, 2, 3, True), _fixture(3, 1, 3, 1, True),
    _fixture(4, 2, 1, 2, False), _fixture(5, 2, 3, 1, False),
    _fixture(6, 3, 1, 2, False),
]


def _player(pid, team):
    return {"id": pid, "web_name": f"Mid{team}", "team": team, "element_type": 3, "status": "a",
            "chance_of_playing_next_round": None, "starts": 2, "minutes": 180,
            "expected_goals": "0.50", "expected_assists": "0.20", "defensive_contribution": 16,
            "bonus": 2, "saves": 0}


BOOTSTRAP = {
    "events": [{"id": 1, "is_next": False}, {"id": 2, "is_next": True}, {"id": 3, "is_next": False}],
    "teams": TEAMS,
    "element_types": [{"id": 1, "singular_name_short": "GKP"}, {"id": 2, "singular_name_short": "DEF"},
                      {"id": 3, "singular_name_short": "MID"}, {"id": 4, "singular_name_short": "FWD"}],
    "elements": [_player(1, 1), _player(2, 2), _player(3, 3)],
    "game_config": {"scoring": {
        "clean_sheets": {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0},
        "goals_conceded": {"GKP": -1, "DEF": -1, "MID": 0, "FWD": 0},
        "defensive_contribution": {"GKP": 0, "DEF": 2, "MID": 2, "FWD": 2},
        "goals_scored": {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4},
        "assists": 3,
    }},
}

AVERAGE = TeamStrengths(table=pd.DataFrame({"attack": [1.0] * 3, "defence_weakness": [1.0] * 3},
                                           index=["A", "B", "C"]), home_rate=1.4, away_rate=1.2)


@pytest.fixture
def fake_league(monkeypatch):
    monkeypatch.setattr(fetch, "get_bootstrap_static", lambda: BOOTSTRAP)
    monkeypatch.setattr(fetch, "get_fixtures", lambda: FIXTURES)
    for module in (defensive_points, attacking_points):
        monkeypatch.setattr(module, "_league_context", lambda: (["A", "B", "C"], [], []))
        monkeypatch.setattr(module, "load_matches", lambda: None)
        monkeypatch.setattr(module, "fit_team_strengths", lambda *args, **kwargs: AVERAGE)


def test_double_gameweek_counts_both_matches(fake_league):
    gw2 = project_next_gameweek(2).set_index("id")
    assert gw2.loc[1, "matches"] == 2                 # A: double
    assert gw2.loc[2, "matches"] == 1
    # Playing points, bonus and defensive contributions are per match: exactly double.
    for part in ("xp_appearance", "xp_bonus", "xp_defensive_contribution"):
        assert gw2.loc[1, part] == pytest.approx(2 * gw2.loc[2, part])
    # A's total is the sum of its two matches: home v B (like B's away match, mirrored) and away at C.
    assert gw2.loc[1, "xp_total"] > 1.8 * gw2.loc[2, "xp_total"]


def test_blank_gameweek_scores_zero(fake_league):
    gw3 = project_next_gameweek(3).set_index("id")
    assert gw3.loc[3, "matches"] == 0                 # C: blank
    assert gw3.loc[3, "xp_total"] == 0.0
    assert gw3.loc[1, "xp_total"] > 0                 # A and B still play
