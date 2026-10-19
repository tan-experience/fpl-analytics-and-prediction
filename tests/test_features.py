"""Tests for fixture handling in src/features.py."""

from src.features import _next_fixture_difficulty, _upcoming_fixtures_for_team


def _fixture(event, team_h, team_a, finished=False, provisional=False, h_diff=3, a_diff=3):
    return {"event": event, "team_h": team_h, "team_a": team_a,
            "finished": finished, "finished_provisional": provisional,
            "team_h_difficulty": h_diff, "team_a_difficulty": a_diff}


def test_provisionally_finished_match_is_not_upcoming():
    # FPL marks a match "finished_provisional" as soon as it ends, but only
    # flips "finished" once bonus points are confirmed - sometimes days later.
    # A match that's been played must not count as the team's next fixture.
    played = _fixture(7, team_h=1, team_a=2, finished=False, provisional=True, h_diff=5)
    next_one = _fixture(8, team_h=1, team_a=3, h_diff=2)
    assert _upcoming_fixtures_for_team(1, [played, next_one]) == [next_one]
    assert _next_fixture_difficulty(1, [played, next_one]) == 2


def test_unplayed_match_is_upcoming():
    unplayed = _fixture(7, team_h=1, team_a=2)
    assert _upcoming_fixtures_for_team(1, [unplayed]) == [unplayed]
