"""
attacking_points.py
-------------------
Phase 3, step 4: expected points from goals and assists.

Run it from the project root:

    python -m src.attacking_points

How it works, for each player's match(es) in the next gameweek:
1. Their scoring RATE: expected goals (xG) and expected assists (xA) per
   90 minutes this season. xG measures the quality of chances a player
   gets (a penalty is ~0.8, a long shot ~0.03), so it's a steadier guide
   than actual goals, which swing on luck. FPL provides both.
   Players with few minutes are pulled towards their position's average.
2. Adjusted for the OPPONENT: the team model (step 1) says how leaky
   each opponent's defence is, plus the home/away effect. Against a side
   that concedes 30% more than average, the player's rates go up 30%.
   Only the opponent is adjusted for - the player's own xG already
   reflects how good their team's attack is this season. (An earlier
   version also re-rated the player's own team using the team model; the
   backtest showed that slightly HURT, because it dragged this season's
   strong attacks back towards last season. See DECISIONS.md.)
3. Times their expected MINUTES: average minutes per team match so far,
   times FPL's injury chance.
4. Points = expected goals x goal value for their position (DEF 6, MID 5,
   FWD 4, from FPL's scoring settings) + expected assists x 3.
"""

import numpy as np
import pandas as pd

from src import fetch
from src.defensive_points import team_matches_played
from src.team_strength import _league_context, fit_team_strengths, load_matches

# How strongly a player's rates are pulled towards their position's
# average, in minutes of "imaginary average playing time" (3 matches).
PRIOR_MINUTES = 270


def shrunk_per_90(total: float, minutes: float, position_rate: float) -> float:
    """
    A player's per-90 rate, pulled towards the position average. With no
    minutes it IS the position average; with lots, it's close to their own.
    """
    return (total + position_rate * PRIOR_MINUTES / 90) / ((minutes + PRIOR_MINUTES) / 90)


def _assist_points(scoring: dict, position: str) -> float:
    """FPL stores the assist value as one number for everyone; goals vary by position."""
    value = scoring["assists"]
    return value[position] if isinstance(value, dict) else value


def expected_attacking(xg90: float, xa90: float, expected_minutes: float,
                       opponent_factor: float, position: str, scoring: dict) -> tuple:
    """
    (expected goals, expected assists, expected points) for one match.
    opponent_factor: >1 = easier than usual to score against (from
                     TeamStrengths.opponent_factor), 1 = average opponent
    """
    scale = opponent_factor * expected_minutes / 90
    goals, assists = xg90 * scale, xa90 * scale
    points = goals * scoring["goals_scored"][position] + assists * _assist_points(scoring, position)
    return goals, assists, points


def evaluate(history: pd.DataFrame, gameweeks: list, scoring: dict) -> pd.DataFrame:
    """
    Leakage-free backtest. For each gameweek, uses only earlier matches for
    each player's rates and minutes, plus the opponent factor for that
    match (column opponent_factor, from a team model fitted on earlier
    matches only), and compares with the goal/assist points they actually
    scored.

    history columns: element, position, team, fixture, gameweek, minutes,
    expected_goals, expected_assists, goals_scored, assists, opponent_factor
    Returns one row per player-match with:
      predicted:            this model
      predicted_no_fixture: same, without the opponent adjustment
      recent_average:       goal/assist points per match so far (a form-like baseline)
      actual:               goal/assist points actually scored
    """
    history = history[history["position"] != "GKP"].copy()
    history["points"] = (
        history["goals_scored"] * history["position"].map(scoring["goals_scored"])
        + history["assists"] * history["position"].map(lambda p: _assist_points(scoring, p))
    )

    rows = []
    for gw in gameweeks:
        before = history[history["gameweek"] < gw]
        this_gw = history[history["gameweek"] == gw]
        if before.empty:
            continue

        totals = before.groupby("position")[["expected_goals", "expected_assists", "minutes"]].sum()
        pos_xg90 = totals["expected_goals"] / (totals["minutes"] / 90)
        pos_xa90 = totals["expected_assists"] / (totals["minutes"] / 90)

        per_player = before.groupby("element").agg(
            xg=("expected_goals", "sum"), xa=("expected_assists", "sum"),
            minutes=("minutes", "sum"), matches=("fixture", "count"), points=("points", "sum"),
        )

        for m in this_gw.itertuples():
            if m.element in per_player.index:
                p = per_player.loc[m.element]
                xg, xa, minutes, matches, points = p["xg"], p["xa"], p["minutes"], p["matches"], p["points"]
            else:
                xg = xa = minutes = points = 0.0
                matches = 0
            xg90 = shrunk_per_90(xg, minutes, pos_xg90.get(m.position, 0.0))
            xa90 = shrunk_per_90(xa, minutes, pos_xa90.get(m.position, 0.0))
            expected_minutes = minutes / matches if matches else 0.0

            predicted = expected_attacking(xg90, xa90, expected_minutes, m.opponent_factor,
                                           m.position, scoring)[2]
            no_fixture = expected_attacking(xg90, xa90, expected_minutes, 1.0,
                                            m.position, scoring)[2]
            rows.append({
                "gameweek": gw, "element": m.element, "position": m.position,
                "predicted": predicted, "predicted_no_fixture": no_fixture,
                "recent_average": points / matches if matches else 0.0,
                "actual": m.points,
            })
    return pd.DataFrame(rows)


def next_gameweek_attack(gameweek: int = None) -> pd.DataFrame:
    """
    Expected goals, assists and their points for every outfield player in
    the next deadline's gameweek, from FPL's main data file plus the team
    model. Double gameweeks add both matches; blank gameweeks give 0.
    """
    bootstrap = fetch.get_bootstrap_static()
    fixtures = fetch.get_fixtures()
    scoring = bootstrap["game_config"]["scoring"]
    if gameweek is None:
        gameweek = next(e["id"] for e in bootstrap["events"] if e["is_next"])

    teams_by_id = {t["id"]: t["name"] for t in bootstrap["teams"]}
    positions = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    team_matches = team_matches_played(fixtures, teams_by_id)
    teams, promoted, relegated = _league_context()

    gw_fixtures = [f for f in fixtures if f["event"] == gameweek]
    first_kickoff = pd.Timestamp(min(f["kickoff_time"] for f in gw_fixtures))
    strengths = fit_team_strengths(load_matches(), first_kickoff, teams, promoted, relegated)
    opponent_factors = {name: [] for name in teams_by_id.values()}
    for f in gw_fixtures:
        home, away = teams_by_id[f["team_h"]], teams_by_id[f["team_a"]]
        opponent_factors[home].append(strengths.opponent_factor(away, is_home=True))
        opponent_factors[away].append(strengths.opponent_factor(home, is_home=False))

    players = pd.DataFrame([{
        "id": p["id"], "web_name": p["web_name"], "team": teams_by_id[p["team"]],
        "position": positions[p["element_type"]], "minutes": p["minutes"],
        "xg": float(p["expected_goals"]), "xa": float(p["expected_assists"]),
        "status": p["status"], "chance": p["chance_of_playing_next_round"],
    } for p in bootstrap["elements"] if positions[p["element_type"]] in ("DEF", "MID", "FWD")])

    by_pos = players.groupby("position")[["xg", "xa", "minutes"]].sum()
    pos_xg90 = by_pos["xg"] / (by_pos["minutes"] / 90)
    pos_xa90 = by_pos["xa"] / (by_pos["minutes"] / 90)

    rows = []
    for p in players.itertuples():
        if p.status in ("i", "s", "u", "n") or team_matches[p.team] == 0:
            fitness = 0.0
        elif p.chance is None or pd.isna(p.chance):
            fitness = 1.0
        else:
            fitness = p.chance / 100
        expected_minutes = p.minutes / team_matches[p.team] * fitness if team_matches[p.team] else 0.0
        xg90 = shrunk_per_90(p.xg, p.minutes, pos_xg90[p.position])
        xa90 = shrunk_per_90(p.xa, p.minutes, pos_xa90[p.position])
        goals = assists = points = 0.0
        for factor in opponent_factors[p.team]:
            g, a, pts = expected_attacking(xg90, xa90, expected_minutes, factor, p.position, scoring)
            goals, assists, points = goals + g, assists + a, points + pts
        rows.append({"id": p.id, "web_name": p.web_name, "team": p.team, "position": p.position,
                     "expected_minutes": expected_minutes, "expected_goals": goals,
                     "expected_assists": assists, "expected_attacking_points": points})
    return pd.DataFrame(rows)


def _rank_corr(rows: pd.DataFrame, column: str) -> float:
    return rows.groupby("gameweek").apply(
        lambda g: g[column].rank().corr(g["actual"].rank()), include_groups=False
    ).mean()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    from src.backtest import _load_histories

    bootstrap = fetch.get_bootstrap_static()
    scoring = bootstrap["game_config"]["scoring"]
    next_gw = next(e["id"] for e in bootstrap["events"] if e["is_next"])

    table = next_gameweek_attack(next_gw)
    print(f"Gameweek {next_gw}: highest expected goal + assist points\n")
    print(table.nlargest(12, "expected_attacking_points")[[
        "web_name", "team", "position", "expected_minutes", "expected_goals",
        "expected_assists", "expected_attacking_points"]].round(2).to_string(index=False))

    # Backtest: build match-by-match history with each player's team and the
    # opponent factor for that match (team model fitted before each gameweek).
    teams_by_id = {t["id"]: t["name"] for t in bootstrap["teams"]}
    positions = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    fixtures = {f["id"]: f for f in fetch.get_fixtures()}
    players = [p for p in bootstrap["elements"] if p["minutes"] > 0]
    print(f"\nLoading match history for {len(players)} players...")
    history = pd.DataFrame(_load_histories([p["id"] for p in players]))
    history = history.rename(columns={"round": "gameweek"})
    history["position"] = history["element"].map({p["id"]: positions[p["element_type"]] for p in players})
    history["team"] = history.apply(
        lambda r: teams_by_id[fixtures[r["fixture"]]["team_h" if r["was_home"] else "team_a"]], axis=1)
    for col in ("expected_goals", "expected_assists"):
        history[col] = history[col].astype(float)

    matches = load_matches()
    teams, promoted, relegated = _league_context()
    gameweeks = sorted(history["gameweek"].unique())[2:]
    factors = {}
    for gw in gameweeks:
        gw_fixtures = [f for f in fixtures.values() if f["event"] == gw]
        strengths = fit_team_strengths(matches, pd.Timestamp(min(f["kickoff_time"] for f in gw_fixtures)),
                                       teams, promoted, relegated)
        for f in gw_fixtures:
            home, away = teams_by_id[f["team_h"]], teams_by_id[f["team_a"]]
            factors[(f["id"], home)] = strengths.opponent_factor(away, is_home=True)
            factors[(f["id"], away)] = strengths.opponent_factor(home, is_home=False)
    history["opponent_factor"] = [factors.get((f, t), np.nan) for f, t in zip(history["fixture"], history["team"])]

    rows = evaluate(history, gameweeks, scoring)
    print(f"\nPredicting goal + assist points, gameweeks {gameweeks[0]}-{gameweeks[-1]} "
          f"({len(rows)} player-matches, all outfield players):")
    for label, column in [("This model (xG/xA rates x opponent x minutes)", "predicted"),
                          ("Same, without the opponent adjustment", "predicted_no_fixture"),
                          ("Goal/assist points per match so far", "recent_average")]:
        mae = (rows[column] - rows["actual"]).abs().mean()
        print(f"  rank corr {_rank_corr(rows, column):.3f}   MAE {mae:.3f}   total {rows[column].sum():7.1f}   {label}")
    print(f"  (actual total: {rows['actual'].sum():.0f} points)")
