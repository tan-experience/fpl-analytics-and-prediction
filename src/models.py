"""
models.py
---------
Projection and prediction models live here. We're starting with a weighted
HEURISTIC (a formula, not a trained model) for player points - this gives
us a baseline to compare any future machine-learning model against. If an
ML model can't beat this simple formula, it's not worth using.

The formula, in plain English:
  projected_points = (probability they play) x (recent form, adjusted for
                      how hard their next fixture is)

Why these three ingredients:
- Recent form is FPL's own rolling average of points per match - already a
  decent predictor on its own.
- Fixture difficulty adjusts that up or down: a good run of form against a
  weak opponent is worth more than against a title-chasing defense.
- Probability of playing matters because even a great projection is worth
  zero if the player is injured/rested - this discounts for that risk.
"""

import pandas as pd

from src.features import build_player_features

# Tunable weights - these are a starting guess, not derived from data yet.
# Once we have Phase 2 backtesting (comparing projections to what actually
# happened), we can tune these properly instead of guessing.
FIXTURE_DIFFICULTY_WEIGHT = 0.15  # points added/removed per difficulty step away from average (3)
AVERAGE_DIFFICULTY = 3


def _fixture_adjustment(difficulty) -> float:
    """
    Converts a 1-5 fixture difficulty into a points adjustment.
    Difficulty 1 (easiest) -> positive adjustment.
    Difficulty 5 (hardest) -> negative adjustment.
    Missing difficulty (no fixture found) -> no adjustment.
    """
    if difficulty is None or pd.isna(difficulty):
        return 0.0
    return (AVERAGE_DIFFICULTY - difficulty) * FIXTURE_DIFFICULTY_WEIGHT


def _playing_probability(chance_of_playing) -> float:
    """
    FPL gives chance_of_playing_next_round as 0-100, or None if there's no
    injury/rotation doubt at all (i.e. treat as 100).
    """
    if chance_of_playing is None or pd.isna(chance_of_playing):
        return 1.0
    return chance_of_playing / 100


def project_gameweek_points(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds a 'projected_points' column to a player features DataFrame
    (as built by features.build_player_features()).
    """
    df = df.copy()

    df["fixture_adjustment"] = df["next_fixture_difficulty"].apply(_fixture_adjustment)
    df["playing_probability"] = df["chance_of_playing_next_round"].apply(_playing_probability)

    df["projected_points"] = df["playing_probability"] * (
        df["form"] + df["fixture_adjustment"]
    )

    # Never project below 0. A player with no form facing a hard fixture
    # would otherwise come out slightly negative (e.g. -0.15) - but a tough
    # opponent alone shouldn't predict a player LOSING points.
    df["projected_points"] = df["projected_points"].clip(lower=0)

    # Players marked unavailable (injured/suspended/left the club) shouldn't
    # show a meaningful projection regardless of stale form numbers.
    df.loc[df["status"] != "a", "projected_points"] = 0.0

    return df


if __name__ == "__main__":
    # Manual test: run `python -m src.models` from the project root.
    features_df = build_player_features()
    projected = project_gameweek_points(features_df)

    print("Top 15 projected scorers for the next gameweek:\n")
    print(
        projected.sort_values("projected_points", ascending=False)
        .head(15)[["web_name", "team", "position", "now_cost", "projected_points"]]
        .to_string(index=False)
    )
