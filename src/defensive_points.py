"""
defensive_points.py
-------------------
Phase 3, step 2: expected points from clean sheets and goals conceded, for
every player's matches in the next gameweek.

Run it from the project root:

    python -m src.defensive_points

FPL's rules (read from the API's own scoring settings, not typed in here):
- Clean sheet (team concedes 0, player plays 60+ minutes):
  GKP/DEF +4, MID +1, FWD 0
- Goals conceded: GKP/DEF lose 1 point for every 2 goals conceded

How we estimate them:
- The team model (team_strength.py) gives the OPPONENT's expected goals.
  The chance they score 0 - our clean sheet - is e^(-expected goals).
- The same "Poisson" maths gives the expected number of 2-goal deductions.
- Both only count if the player plays 60+ minutes. We estimate that as the
  share of their team's matches this season they've started, reduced by
  FPL's injury percentage. (Simplification: a few starters get subbed off
  before 60 minutes; we ignore that for now.)
"""

import math

import numpy as np
import pandas as pd

from src import fetch
from src.team_strength import (
    _league_context,
    evaluate,
    fit_team_strengths,
    load_matches,
)

# The most goals worth adding up when working out expected deductions -
# the chance of more than this many is effectively zero.
MAX_GOALS = 15


def clean_sheet_probability(opponent_expected_goals: float) -> float:
    """Chance the opponent scores 0: e^(-expected goals) under a Poisson model."""
    return math.exp(-opponent_expected_goals)


def expected_conceded_penalty(opponent_expected_goals: float) -> float:
    """
    Expected number of "every 2 goals conceded" deductions: the chance of
    conceding exactly k goals, times how many deductions k goals cause
    (0 for 0-1 goals, 1 for 2-3, 2 for 4-5...), added up over every k.
    """
    lam = opponent_expected_goals
    return sum(
        (k // 2) * math.exp(-lam) * lam ** k / math.factorial(k)
        for k in range(MAX_GOALS + 1)
    )


def play_probability(starts: int, team_matches: int, status: str, chance_of_playing) -> float:
    """
    Rough chance a player plays 60+ minutes next match: how often they've
    started this season, times FPL's injury chance (if any).
    """
    if status in ("i", "s", "u", "n") or team_matches == 0:
        return 0.0  # injured, suspended, left the club, not available - or no evidence yet
    start_rate = min(starts / team_matches, 1.0)
    fitness = 1.0 if chance_of_playing is None or pd.isna(chance_of_playing) else chance_of_playing / 100
    return start_rate * fitness


def expected_defensive_points(position: str, opponent_expected_goals: float,
                              p60: float, scoring: dict) -> float:
    """Expected clean-sheet points plus (negative) goals-conceded points for one match."""
    clean_sheet = scoring["clean_sheets"][position] * clean_sheet_probability(opponent_expected_goals)
    conceded = scoring["goals_conceded"][position] * expected_conceded_penalty(opponent_expected_goals)
    return p60 * (clean_sheet + conceded)


def score_clean_sheet_predictions(rows: pd.DataFrame) -> dict:
    """
    How good were our clean-sheet chances? `rows` has one row per team per
    match, where "predicted"/"actual" are the OPPONENT's expected/actual goals
    (that's the shape team_strength.evaluate() returns, read from the other side).

    Brier score = average of (predicted chance - what happened)^2, where what
    happened is 1 for a clean sheet and 0 otherwise. 0 is perfect; always
    saying 50% scores 0.25. Lower is better.
    """
    chance = np.exp(-rows["predicted"])
    kept = (rows["actual"] == 0).astype(float)
    return {
        "brier": float(((chance - kept) ** 2).mean()),
        "clean_sheets": int(kept.sum()),
        "predicted_clean_sheets": float(chance.sum()),
    }


def next_gameweek_defence(gameweek: int = None) -> pd.DataFrame:
    """
    Expected clean-sheet and goals-conceded points for every player in the
    next deadline's gameweek (or the given one). Players with two matches
    that week (a "double gameweek") get both added; no match = 0.
    """
    bootstrap = fetch.get_bootstrap_static()
    fixtures = fetch.get_fixtures()
    scoring = bootstrap["game_config"]["scoring"]
    if gameweek is None:
        gameweek = next(e["id"] for e in bootstrap["events"] if e["is_next"])

    teams_by_id = {t["id"]: t["name"] for t in bootstrap["teams"]}
    positions = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    teams, promoted, relegated = _league_context()

    gw_fixtures = [f for f in fixtures if f["event"] == gameweek]
    first_kickoff = pd.Timestamp(min(f["kickoff_time"] for f in gw_fixtures))
    strengths = fit_team_strengths(load_matches(), first_kickoff, teams, promoted, relegated)

    # Each team's opponents' expected goals in this gameweek (0, 1 or 2 matches).
    opponent_goals = {name: [] for name in teams_by_id.values()}
    for f in gw_fixtures:
        home, away = teams_by_id[f["team_h"]], teams_by_id[f["team_a"]]
        exp_home, exp_away = strengths.expected_goals(home, away)
        opponent_goals[home].append(exp_away)
        opponent_goals[away].append(exp_home)

    # How many matches each team has played so far (for the start rate).
    team_matches = {name: 0 for name in teams_by_id.values()}
    for f in fixtures:
        if f["finished_provisional"]:
            team_matches[teams_by_id[f["team_h"]]] += 1
            team_matches[teams_by_id[f["team_a"]]] += 1

    rows = []
    for p in bootstrap["elements"]:
        team, position = teams_by_id[p["team"]], positions[p["element_type"]]
        if position not in scoring["clean_sheets"]:
            continue  # e.g. FPL's "manager" pseudo-players
        p60 = play_probability(p["starts"], team_matches[team], p["status"],
                               p["chance_of_playing_next_round"])
        matches = opponent_goals[team]
        rows.append({
            "id": p["id"],
            "web_name": p["web_name"],
            "team": team,
            "position": position,
            "matches": len(matches),
            "p60": p60,
            "clean_sheet_chance": float(np.mean([clean_sheet_probability(g) for g in matches])) if matches else 0.0,
            "expected_defensive_points": sum(
                expected_defensive_points(position, g, p60, scoring) for g in matches
            ),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")  # so names like "Šešmić" print on Windows

    bootstrap = fetch.get_bootstrap_static()
    next_gw = next(e["id"] for e in bootstrap["events"] if e["is_next"])
    table = next_gameweek_defence(next_gw)

    print(f"Gameweek {next_gw}: top expected clean-sheet + goals-conceded points\n")
    for pos in ("GKP", "DEF"):
        top = table[table["position"] == pos].nlargest(8, "expected_defensive_points")
        print(f"{pos}:")
        print(top[["web_name", "team", "matches", "p60", "clean_sheet_chance",
                   "expected_defensive_points"]].round(2).to_string(index=False))
        print()

    # Did our clean-sheet chances come true at the rates we predicted?
    matches = load_matches()
    teams, promoted, relegated = _league_context()
    gameweeks = sorted(matches["gameweek"].dropna().unique())[1:]
    rows = evaluate(matches, teams, gameweeks, promoted, relegated)
    model = score_clean_sheet_predictions(rows)

    # Baseline: give every team the same chance - last season's overall
    # clean-sheet rate (known before this season, so no peeking).
    last = matches[matches["gameweek"].isna()]
    base_rate = float(((last["home_goals"] == 0).sum() + (last["away_goals"] == 0).sum()) / (2 * len(last)))
    kept = (rows["actual"] == 0).astype(float)
    baseline_brier = float(((base_rate - kept) ** 2).mean())

    print(f"Clean-sheet predictions, gameweeks {int(gameweeks[0])}-{int(gameweeks[-1])} "
          f"({len(rows)} team-matches, {model['clean_sheets']} actual clean sheets; "
          f"model expected {model['predicted_clean_sheets']:.1f}):")
    print(f"  Brier score, model:                                  {model['brier']:.3f}")
    print(f"  Brier score, same chance for everyone ({base_rate:.0%}):       {baseline_brier:.3f}")
    print("  (Brier: average squared gap between predicted chance and what happened - lower is better.)")

    # Calibration: when we said ~X%, did it happen ~X% of the time?
    chance = np.exp(-rows["predicted"])
    buckets = pd.cut(chance, [0, 0.2, 0.3, 0.4, 1.0], labels=["<20%", "20-30%", "30-40%", "40%+"])
    calibration = pd.DataFrame({"predicted": chance, "kept": kept, "bucket": buckets}).groupby(
        "bucket", observed=True).agg(matches=("kept", "size"), predicted=("predicted", "mean"),
                                     actual=("kept", "mean"))
    print("\nWhen we predicted... (did it happen that often?)")
    print(calibration.round(2).to_string())
