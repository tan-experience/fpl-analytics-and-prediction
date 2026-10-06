"""
team_strength.py
----------------
Phase 3, step 1: how strong is each team, and how many goals should we
expect in each upcoming match?

Run it from the project root:

    python -m src.team_strength

The idea (a standard "Poisson" football model):
- Every team gets an ATTACK rating (1.3 = scores 30% more than an average
  team would) and a DEFENCE WEAKNESS rating (1.3 = concedes 30% more).
- Expected goals for the home side in a match =
      home_rate x home attack x away defence weakness
  and the same for the away side with away_rate. home_rate and away_rate
  are the league's average goals per match at home / away, which is how
  home advantage gets in.
- "Poisson" is the name of the probability distribution that turns an
  expected number of goals (say 1.4) into chances of 0, 1, 2... goals. For
  example, the chance of scoring 0 is e^(-1.4) = 25% - which is also the
  OTHER team's clean-sheet chance. That's what makes this useful for FPL.

How the ratings are worked out:
- From last season's results (football-data.co.uk) plus this season's (FPL
  API). Recent matches count more: a match HALF_LIFE_DAYS ago counts half
  as much as one today.
- Each rating is also nudged towards a starting guess ("prior"), as if the
  team had played PRIOR_MATCHES extra average matches. This stops a single
  freak result (one 6-0) from producing extreme ratings.
- Newly promoted teams have no Premier League data from last season, so
  their starting guess is the average of last season's relegated teams -
  a common rule of thumb: promoted sides tend to be about that strong.
"""

import io
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import fetch

# A match this many days ago counts half as much as one played today.
HALF_LIFE_DAYS = 120

# How strongly ratings are pulled towards their starting guess, measured
# in "imaginary average matches".
PRIOR_MATCHES = 4

# football-data.co.uk spells a few teams differently from FPL.
TEAM_NAME_FIXES = {"Man United": "Man Utd", "Tottenham": "Spurs"}

# How many rounds of refinement to run when fitting (see fit_team_strengths).
FIT_ITERATIONS = 200


@dataclass
class TeamStrengths:
    """
    The fitted model. (A "dataclass" is just a tidy way to bundle a few
    related values together under one name.)

    table:     one row per team, columns "attack" and "defence_weakness"
    home_rate: average goals per match scored by home sides
    away_rate: average goals per match scored by away sides
    """
    table: pd.DataFrame
    home_rate: float
    away_rate: float

    def expected_goals(self, home: str, away: str) -> tuple:
        """(home team's expected goals, away team's expected goals) for one match."""
        h, a = self.table.loc[home], self.table.loc[away]
        return (
            self.home_rate * h["attack"] * a["defence_weakness"],
            self.away_rate * a["attack"] * h["defence_weakness"],
        )


def load_matches() -> pd.DataFrame:
    """
    All finished matches we know about - last season's and this season's -
    in one table with columns: date, home, away, home_goals, away_goals,
    gameweek (this season only; empty for last season), and FPL's 1-5
    difficulty for each side (this season only, used as a comparison).
    """
    last = pd.read_csv(io.StringIO(fetch.get_last_season_results()))
    last = pd.DataFrame({
        "date": pd.to_datetime(last["Date"], dayfirst=True).dt.tz_localize("UTC"),
        "home": last["HomeTeam"].replace(TEAM_NAME_FIXES),
        "away": last["AwayTeam"].replace(TEAM_NAME_FIXES),
        "home_goals": last["FTHG"],
        "away_goals": last["FTAG"],
        "gameweek": np.nan,
        "home_difficulty": np.nan,
        "away_difficulty": np.nan,
    })

    teams_by_id = {t["id"]: t["name"] for t in fetch.get_bootstrap_static()["teams"]}
    current = pd.DataFrame([
        {
            "date": pd.Timestamp(f["kickoff_time"]),
            "home": teams_by_id[f["team_h"]],
            "away": teams_by_id[f["team_a"]],
            "home_goals": f["team_h_score"],
            "away_goals": f["team_a_score"],
            "gameweek": f["event"],
            "home_difficulty": f["team_h_difficulty"],
            "away_difficulty": f["team_a_difficulty"],
        }
        for f in fetch.get_fixtures() if f["finished"]
    ])
    return pd.concat([last, current], ignore_index=True)


def fit_team_strengths(matches: pd.DataFrame, as_of: pd.Timestamp, teams: list,
                       promoted=(), relegated=()) -> TeamStrengths:
    """
    Works out every team's attack and defence weakness, using only matches
    played BEFORE `as_of` (so the backtest can never peek at results it's
    trying to predict).

    teams:     the teams to report (this season's league)
    promoted:  teams with no data of their own last season
    relegated: last season's teams whose average becomes the promoted
               teams' starting guess

    How the fitting works: start with every rating at 1 (average), then
    repeatedly ask "given everyone else's current ratings, what rating best
    explains this team's actual goals?" and update. Each round improves the
    fit; after a couple of hundred rounds the numbers stop changing. (This
    gives the same answer as the statistical "maximum likelihood" method.)
    """
    past = matches[matches["date"] < as_of]
    names = sorted(set(teams) | set(past["home"]) | set(past["away"]))
    index = {name: i for i, name in enumerate(names)}
    n = len(names)

    home = past["home"].map(index).to_numpy()
    away = past["away"].map(index).to_numpy()
    hg = past["home_goals"].to_numpy(dtype=float)
    ag = past["away_goals"].to_numpy(dtype=float)

    # Recency weight: 1 for a match today, 0.5 at HALF_LIFE_DAYS ago, etc.
    days_ago = (as_of - past["date"]).dt.total_seconds().to_numpy() / 86400
    w = 0.5 ** (days_ago / HALF_LIFE_DAYS)

    # Average goals per team per match - used to size the "imaginary
    # matches" that pull ratings towards their starting guess.
    goals_per_team_match = (w @ hg + w @ ag) / (2 * w.sum()) if len(past) else 1.4
    pseudo = PRIOR_MATCHES * goals_per_team_match

    promoted_idx = [index[t] for t in promoted if t in index]
    relegated_idx = [index[t] for t in relegated if t in index]

    attack = np.ones(n)
    weakness = np.ones(n)
    home_rate = away_rate = goals_per_team_match

    for _ in range(FIT_ITERATIONS):
        if len(past):
            home_rate = (w @ hg) / (w @ (attack[home] * weakness[away]))
            away_rate = (w @ ag) / (w @ (attack[away] * weakness[home]))

        # Starting guesses: average (1.0) for everyone, except promoted teams,
        # who start at the relegated teams' current average.
        prior_attack, prior_weakness = np.ones(n), np.ones(n)
        if promoted_idx and relegated_idx:
            prior_attack[promoted_idx] = attack[relegated_idx].mean()
            prior_weakness[promoted_idx] = weakness[relegated_idx].mean()

        # Attack = goals actually scored / goals an average attack would have
        # scored against the same opponents (plus the imaginary matches).
        # np.bincount adds up values per team.
        scored = np.bincount(home, w * hg, n) + np.bincount(away, w * ag, n)
        expected_if_average = (np.bincount(home, w * weakness[away] * home_rate, n)
                               + np.bincount(away, w * weakness[home] * away_rate, n))
        attack = (scored + pseudo * prior_attack) / (expected_if_average + pseudo)

        # Defence weakness: the same idea, for goals conceded.
        conceded = np.bincount(away, w * hg, n) + np.bincount(home, w * ag, n)
        expected_if_average = (np.bincount(away, w * attack[home] * home_rate, n)
                               + np.bincount(home, w * attack[away] * away_rate, n))
        weakness = (conceded + pseudo * prior_weakness) / (expected_if_average + pseudo)

        # Keep this season's teams averaging exactly 1, so "1.3" always means
        # "30% above an average team in this league".
        current = [index[t] for t in teams]
        attack /= attack[current].mean()
        weakness /= weakness[current].mean()

    table = pd.DataFrame(
        {"attack": attack, "defence_weakness": weakness}, index=names
    ).loc[list(teams)]
    return TeamStrengths(table=table, home_rate=home_rate, away_rate=away_rate)


def evaluate(matches: pd.DataFrame, teams: list, gameweeks: list,
             promoted=(), relegated=(), use_last_season: bool = True) -> pd.DataFrame:
    """
    The backtest for this model: for each gameweek, fit the ratings using
    only matches from before that gameweek started, predict every match in
    it, and record the prediction next to what actually happened.

    Returns one row per team per match: gameweek, team, predicted goals,
    actual goals, and FPL's 1-5 difficulty for that team (for comparison).
    """
    if not use_last_season:
        matches = matches[matches["gameweek"].notna()]

    rows = []
    for gw in gameweeks:
        this_gw = matches[matches["gameweek"] == gw]
        strengths = fit_team_strengths(
            matches, this_gw["date"].min(), teams, promoted, relegated
        )
        for m in this_gw.itertuples():
            exp_home, exp_away = strengths.expected_goals(m.home, m.away)
            rows.append({"gameweek": gw, "team": m.home, "predicted": exp_home,
                         "actual": m.home_goals, "difficulty": m.home_difficulty})
            rows.append({"gameweek": gw, "team": m.away, "predicted": exp_away,
                         "actual": m.away_goals, "difficulty": m.away_difficulty})
    return pd.DataFrame(rows)


def _rank_corr(predicted: pd.Series, actual: pd.Series, gameweek: pd.Series) -> float:
    """Average per-gameweek rank correlation (same idea as in backtest.py)."""
    df = pd.DataFrame({"p": predicted, "a": actual, "gw": gameweek})
    return df.groupby("gw").apply(
        lambda g: g["p"].rank().corr(g["a"].rank()), include_groups=False
    ).mean()


def _league_context() -> tuple:
    """This season's teams, promoted teams and relegated teams."""
    teams = [t["name"] for t in fetch.get_bootstrap_static()["teams"]]
    last = pd.read_csv(io.StringIO(fetch.get_last_season_results()))
    last_teams = set(last["HomeTeam"].replace(TEAM_NAME_FIXES))
    promoted = [t for t in teams if t not in last_teams]
    relegated = sorted(last_teams - set(teams))
    return teams, promoted, relegated


if __name__ == "__main__":
    matches = load_matches()
    teams, promoted, relegated = _league_context()

    # Check team names line up between the two sources - a mismatch would
    # silently treat one club as two different teams.
    unknown = set(matches["home"]) - set(teams) - set(relegated)
    if unknown:
        raise SystemExit(f"Team names not recognised: {sorted(unknown)}")

    print(f"Promoted (starting at relegated teams' average): {', '.join(promoted)}")
    print(f"Relegated last season: {', '.join(relegated)}\n")

    now = pd.Timestamp.now(tz="UTC")
    strengths = fit_team_strengths(matches, now, teams, promoted, relegated)
    table = strengths.table.sort_values("attack", ascending=False)
    print("Team ratings now (1.00 = league average):")
    print(table.round(2).to_string())

    # Upcoming fixtures: expected goals and clean-sheet chances.
    teams_by_id = {t["id"]: t["name"] for t in fetch.get_bootstrap_static()["teams"]}
    upcoming = [f for f in fetch.get_fixtures() if not f["finished"] and f["event"]]
    next_gw = min(f["event"] for f in upcoming)
    print(f"\nGameweek {next_gw} - expected goals (and each side's clean-sheet chance):")
    for f in sorted((f for f in upcoming if f["event"] == next_gw), key=lambda f: f["kickoff_time"]):
        home, away = teams_by_id[f["team_h"]], teams_by_id[f["team_a"]]
        exp_home, exp_away = strengths.expected_goals(home, away)
        print(f"  {home:>15} {exp_home:.1f} - {exp_away:.1f} {away:<15}"
              f"  clean sheet: {np.exp(-exp_away):.0%} / {np.exp(-exp_home):.0%}")

    # How good is it? Compare on this season's finished gameweeks.
    gameweeks = sorted(matches["gameweek"].dropna().unique())[1:]  # GW1 has no this-season history
    with_last = evaluate(matches, teams, gameweeks, promoted, relegated)
    this_only = evaluate(matches, teams, gameweeks, use_last_season=False)

    results = pd.DataFrame({
        "Model (last season + this season)": {
            "rank_corr": _rank_corr(with_last["predicted"], with_last["actual"], with_last["gameweek"]),
            "mae": (with_last["predicted"] - with_last["actual"]).abs().mean(),
        },
        "Model (this season only)": {
            "rank_corr": _rank_corr(this_only["predicted"], this_only["actual"], this_only["gameweek"]),
            "mae": (this_only["predicted"] - this_only["actual"]).abs().mean(),
        },
        "FPL 1-5 difficulty (easier = more goals)": {
            "rank_corr": _rank_corr(-with_last["difficulty"], with_last["actual"], with_last["gameweek"]),
            "mae": np.nan,  # difficulty isn't in goals, so no goals error
        },
    }).T.sort_values("rank_corr", ascending=False)

    print(f"\nPredicting each team's goals per match, gameweeks "
          f"{int(gameweeks[0])}-{int(gameweeks[-1])} ({len(with_last)} team-matches):")
    print(results.round(3).to_string())
    print("\nrank_corr: did teams expected to score more actually score more? (higher = better)")
    print("mae: average miss in goals (lower = better).")
    print("Caution: a small sample - re-run as the season goes on.")
