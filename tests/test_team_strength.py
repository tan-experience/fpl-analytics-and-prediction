"""
Tests for the team strength model (src/team_strength.py).

They use tiny made-up leagues where the right answer is obvious - e.g. a
league where every match ends 1-1 should rate every team as exactly average.
"""

import pandas as pd
import pytest

from src.team_strength import evaluate, fit_team_strengths

AS_OF = pd.Timestamp("2026-09-01", tz="UTC")


def _match(days_before: int, home: str, away: str, hg: int, ag: int, gameweek=None) -> dict:
    return {
        "date": AS_OF - pd.Timedelta(days=days_before),
        "home": home, "away": away, "home_goals": hg, "away_goals": ag,
        "gameweek": gameweek, "home_difficulty": 3, "away_difficulty": 3,
    }


def _round_robin(score_fn, days_before: int = 10, teams=("A", "B", "C", "D")) -> list:
    """Every team plays every other team home and away; score_fn(home, away) -> (hg, ag)."""
    return [
        _match(days_before, h, a, *score_fn(h, a))
        for h in teams for a in teams if h != a
    ]


def test_identical_teams_are_all_average():
    matches = pd.DataFrame(_round_robin(lambda h, a: (1, 1)))
    strengths = fit_team_strengths(matches, AS_OF, teams=["A", "B", "C", "D"])
    assert strengths.table["attack"].tolist() == pytest.approx([1, 1, 1, 1], abs=1e-6)
    assert strengths.table["defence_weakness"].tolist() == pytest.approx([1, 1, 1, 1], abs=1e-6)


def test_team_that_scores_more_gets_higher_attack():
    # A scores 3 in every match; everyone else scores 1.
    matches = pd.DataFrame(_round_robin(lambda h, a: (3 if h == "A" else 1, 3 if a == "A" else 1)))
    table = fit_team_strengths(matches, AS_OF, teams=["A", "B", "C", "D"]).table
    assert table.loc["A", "attack"] > 1.5
    assert table.loc["B", "attack"] < 1


def test_leaky_team_gets_higher_defence_weakness():
    # Everyone scores 3 against D, and 1 against anyone else.
    matches = pd.DataFrame(_round_robin(lambda h, a: (3 if a == "D" else 1, 3 if h == "D" else 1)))
    table = fit_team_strengths(matches, AS_OF, teams=["A", "B", "C", "D"]).table
    assert table.loc["D", "defence_weakness"] > 1.5
    assert table.loc["A", "defence_weakness"] < 1


def test_home_advantage():
    # Home sides always win 2-1.
    matches = pd.DataFrame(_round_robin(lambda h, a: (2, 1)))
    strengths = fit_team_strengths(matches, AS_OF, teams=["A", "B", "C", "D"])
    home, away = strengths.expected_goals("A", "B")
    assert home == pytest.approx(2, abs=0.01)
    assert away == pytest.approx(1, abs=0.01)


def test_recent_matches_count_more_than_old_ones():
    # A was brilliant a year ago (scored 4s), poor recently (scored 0s).
    old = _round_robin(lambda h, a: (4 if h == "A" else 1, 4 if a == "A" else 1), days_before=365)
    recent = _round_robin(lambda h, a: (0 if h == "A" else 1, 0 if a == "A" else 1), days_before=7)
    table = fit_team_strengths(pd.DataFrame(old + recent), AS_OF, teams=["A", "B", "C", "D"]).table
    assert table.loc["A", "attack"] < 1  # the recent form wins out


def test_matches_on_or_after_as_of_are_ignored():
    # The core "no peeking" rule: a result from after the prediction date
    # must not change the strengths.
    base = _round_robin(lambda h, a: (1, 1))
    future = _match(-3, "A", "B", 9, 0)  # 3 days AFTER as_of
    with_future = fit_team_strengths(pd.DataFrame(base + [future]), AS_OF, teams=["A", "B", "C", "D"])
    without = fit_team_strengths(pd.DataFrame(base), AS_OF, teams=["A", "B", "C", "D"])
    pd.testing.assert_frame_equal(with_future.table, without.table)


def test_promoted_team_starts_at_relegated_teams_average():
    # Last season: R (relegated) was weak - scored 0, conceded 3 every time.
    # P (promoted) has no data at all, so it should inherit R's strength.
    league = ("A", "B", "C", "R")
    matches = pd.DataFrame(_round_robin(
        lambda h, a: (0 if h == "R" else 3 if a == "R" else 1, 0 if a == "R" else 3 if h == "R" else 1),
        teams=league,
    ))
    table = fit_team_strengths(
        matches, AS_OF, teams=["A", "B", "C", "P"], promoted=["P"], relegated=["R"],
    ).table
    assert table.loc["P", "attack"] < 0.7
    assert table.loc["P", "defence_weakness"] > 1.3
    assert "R" not in table.index  # only this season's teams are reported


def test_evaluate_never_uses_the_gameweek_being_predicted():
    # Changing a gameweek's own results must not change its predictions.
    def season(gw2_home_goals):
        rows = _round_robin(lambda h, a: (1, 1), days_before=30)
        for row in rows:
            row["gameweek"] = 1
        rows.append(_match(5, "A", "B", gw2_home_goals, 0, gameweek=2))
        rows.append(_match(5, "C", "D", 1, 1, gameweek=2))
        return pd.DataFrame(rows)

    normal = evaluate(season(1), teams=["A", "B", "C", "D"], gameweeks=[2])
    changed = evaluate(season(7), teams=["A", "B", "C", "D"], gameweeks=[2])
    pd.testing.assert_series_equal(normal["predicted"], changed["predicted"])
    assert len(normal) == 4  # 2 matches x 2 teams
