"""
expected_points.py
------------------
Phase 3, step 5: add up every part of FPL's scoring into one "expected
points" number per player, and test it against the original formula
(recent form + fixture difficulty).

Run it from the project root:

    python -m src.expected_points

The parts, each built in an earlier step:
  appearance              2 x chance of playing 60+ minutes
  clean sheet + conceded  step 2 (defensive_points.py)
  defensive contribution  step 3 (defensive_contributions.py)
  goals and assists       step 4 (attacking_points.py)
  bonus                   bonus points per match so far
  saves (GKP)             saves per match so far / 3

Left out for now (measured as "other" in the backtest): the 1 point for a
substitute appearance under 60 minutes, cards, penalties, own goals.
"""

import numpy as np
import pandas as pd

from src.attacking_points import _assist_points, expected_attacking, shrunk_per_90
from src.backtest import FORM_WINDOW, MIN_PRIOR_MATCHES, add_before_match_features, project
from src.defensive_contributions import THRESHOLDS, hit_probability
from src.defensive_points import expected_defensive_points, play_probability
from src.models import FIXTURE_DIFFICULTY_WEIGHT

PARTS = ["appearance", "clean_sheet_and_conceded", "defensive_contribution",
         "goals_and_assists", "bonus", "saves"]


def actual_components(row: pd.Series, scoring: dict) -> dict:
    """
    Splits the points a player ACTUALLY scored in a match into the same
    parts we predict, so each part can be checked separately. Whatever's
    left over (cards, penalties, own goals, sub appearances' 1 point...)
    goes in "other".
    """
    pos = row["position"]
    appearance = 2 if row["minutes"] >= 60 else 0  # the part we model
    defence = (row["clean_sheets"] * scoring["clean_sheets"][pos]
               + (row["goals_conceded"] // 2) * scoring["goals_conceded"][pos])
    threshold = THRESHOLDS.get(pos)
    dc = scoring["defensive_contribution"][pos] if threshold and row["defensive_contribution"] >= threshold else 0
    attack = row["goals_scored"] * scoring["goals_scored"][pos] + row["assists"] * _assist_points(scoring, pos)
    saves = row["saves"] // 3 if pos == "GKP" else 0
    parts = {
        "appearance": appearance,
        "clean_sheet_and_conceded": defence,
        "defensive_contribution": dc,
        "goals_and_assists": attack,
        "bonus": row["bonus"],
        "saves": saves,
    }
    parts = {k: int(v) for k, v in parts.items()}
    parts["other"] = int(row["total_points"]) - sum(parts.values())
    return parts


def evaluate(history: pd.DataFrame, gameweeks: list, scoring: dict) -> pd.DataFrame:
    """
    Leakage-free backtest of the combined model AND the original formula,
    on exactly the same player-matches: matches the player actually played,
    after at least MIN_PRIOR_MATCHES earlier matches (the same rows the
    original backtest uses, so the comparison is fair).

    For each gameweek, everything about a player comes from earlier
    matches only. The team-model columns (opponent_expected_goals,
    opponent_factor) must likewise come from a model fitted before that
    gameweek. Returns one row per player-match with each predicted part
    (pred_*), the total ("predicted"), the original formula ("old_formula"),
    the actual points, and the actual parts (actual_*).
    """
    history = add_before_match_features(history)  # adds form_before, prior_matches (sorted by kickoff)

    rows = []
    for gw in gameweeks:
        before = history[history["gameweek"] < gw]
        this_gw = history[(history["gameweek"] == gw) & (history["minutes"] > 0)
                          & (history["prior_matches"] >= MIN_PRIOR_MATCHES)]
        if before.empty or this_gw.empty:
            continue

        # Position averages from earlier matches (used to steady low-minute players).
        pos_totals = before.groupby("position")[
            ["defensive_contribution", "expected_goals", "expected_assists", "minutes"]].sum()
        nineties = pos_totals["minutes"] / 90
        pos_dc90 = pos_totals["defensive_contribution"] / nineties
        pos_xg90 = pos_totals["expected_goals"] / nineties
        pos_xa90 = pos_totals["expected_assists"] / nineties

        player = before.groupby("element").agg(
            matches=("fixture", "count"), starts=("starts", "sum"), minutes=("minutes", "sum"),
            dc=("defensive_contribution", "sum"), xg=("expected_goals", "sum"),
            xa=("expected_assists", "sum"), bonus=("bonus", "sum"), saves=("saves", "sum"),
        )

        for m in this_gw.itertuples():
            p = player.loc[m.element]
            pos = m.position
            p60 = play_probability(p["starts"], p["matches"], "a", None)
            exp_minutes = p["minutes"] / p["matches"]

            pred = {
                "appearance": 2 * p60,
                "clean_sheet_and_conceded": expected_defensive_points(
                    pos, m.opponent_expected_goals, p60, scoring),
                "defensive_contribution": p60 * scoring["defensive_contribution"][pos] * hit_probability(
                    pos, p["dc"], p["minutes"], pos_dc90.get(pos, 0.0)),
                "goals_and_assists": 0.0 if pos == "GKP" else expected_attacking(
                    shrunk_per_90(p["xg"], p["minutes"], pos_xg90.get(pos, 0.0)),
                    shrunk_per_90(p["xa"], p["minutes"], pos_xa90.get(pos, 0.0)),
                    exp_minutes, m.opponent_factor, pos, scoring)[2],
                "bonus": p["bonus"] / p["matches"],
                "saves": p["saves"] / p["matches"] / 3 if pos == "GKP" else 0.0,
            }
            actual = actual_components(pd.Series(m._asdict()), scoring)
            rows.append({
                "gameweek": gw, "element": m.element, "position": pos,
                **{f"pred_{k}": v for k, v in pred.items()},
                "predicted": sum(pred.values()),
                "old_formula": project(pd.Series([m.form_before]), pd.Series([m.difficulty]),
                                       FIXTURE_DIFFICULTY_WEIGHT).iloc[0],
                "actual": m.total_points,
                **{f"actual_{k}": v for k, v in actual.items()},
            })
    return pd.DataFrame(rows)


def project_next_gameweek(gameweek: int = None) -> pd.DataFrame:
    """
    The LIVE version: every player's expected points for the next deadline's
    gameweek (or the given one), split into the same parts as the backtest.
    Uses only FPL's main data file plus the team model - no per-player
    history downloads - so the web app stays fast.

    Returns one row per player: id, gameweek, matches (0 = blank gameweek,
    2 = double), one xp_<part> column per part, and xp_total.
    """
    from src import fetch
    from src.attacking_points import next_gameweek_attack
    from src.defensive_contributions import next_gameweek_contributions
    from src.defensive_points import next_gameweek_defence, team_matches_played

    bootstrap = fetch.get_bootstrap_static()
    fixtures = fetch.get_fixtures()
    if gameweek is None:
        gameweek = next(e["id"] for e in bootstrap["events"] if e["is_next"])

    teams_by_id = {t["id"]: t["name"] for t in bootstrap["teams"]}
    positions = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    team_matches = team_matches_played(fixtures, teams_by_id)
    matches_this_gw = {name: 0 for name in teams_by_id.values()}
    for f in fixtures:
        if f["event"] == gameweek:
            matches_this_gw[teams_by_id[f["team_h"]]] += 1
            matches_this_gw[teams_by_id[f["team_a"]]] += 1

    defence = next_gameweek_defence(gameweek).set_index("id")
    contributions = next_gameweek_contributions(gameweek).set_index("id")
    attack = next_gameweek_attack(gameweek).set_index("id")

    rows = []
    for p in bootstrap["elements"]:
        pos = positions[p["element_type"]]
        if pos not in ("GKP", "DEF", "MID", "FWD"):
            continue
        team = teams_by_id[p["team"]]
        played = team_matches[team]
        n = matches_this_gw[team]
        p60 = defence.loc[p["id"], "p60"]
        # Same availability rule as the other parts: out = 0, doubtful = scaled down.
        if p["status"] in ("i", "s", "u", "n"):
            fitness = 0.0
        elif p["chance_of_playing_next_round"] is None:
            fitness = 1.0
        else:
            fitness = p["chance_of_playing_next_round"] / 100
        per_match = (lambda total: total / played * fitness) if played else (lambda total: 0.0)

        parts = {
            "appearance": n * 2 * p60,
            "clean_sheet_and_conceded": defence.loc[p["id"], "expected_defensive_points"],
            "defensive_contribution": contributions.loc[p["id"], "expected_dc_points"],
            "goals_and_assists": attack.loc[p["id"], "expected_attacking_points"] if p["id"] in attack.index else 0.0,
            "bonus": n * per_match(p["bonus"]),
            "saves": n * per_match(p["saves"]) / 3 if pos == "GKP" else 0.0,
        }
        rows.append({"id": p["id"], "gameweek": gameweek, "matches": n,
                     **{f"xp_{k}": float(v) for k, v in parts.items()},
                     "xp_total": float(sum(parts.values()))})
    return pd.DataFrame(rows)


def _rank_corr(rows: pd.DataFrame, column: str) -> float:
    return rows.groupby("gameweek").apply(
        lambda g: g[column].rank().corr(g["actual"].rank()), include_groups=False
    ).mean()


def _load_backtest_history() -> pd.DataFrame:
    """Every player's match history this season, with team, position and team-model columns."""
    from src import fetch
    from src.backtest import _load_histories
    from src.team_strength import _league_context, fit_team_strengths, load_matches

    bootstrap = fetch.get_bootstrap_static()
    teams_by_id = {t["id"]: t["name"] for t in bootstrap["teams"]}
    positions = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    fixtures = {f["id"]: f for f in fetch.get_fixtures()}
    players = [p for p in bootstrap["elements"] if p["minutes"] > 0
               and positions[p["element_type"]] in ("GKP", "DEF", "MID", "FWD")]
    print(f"Loading match history for {len(players)} players...")

    history = pd.DataFrame(_load_histories([p["id"] for p in players]))
    history = history.rename(columns={"round": "gameweek"})
    history["position"] = history["element"].map({p["id"]: positions[p["element_type"]] for p in players})
    history["team"] = [teams_by_id[fixtures[f]["team_h" if home else "team_a"]]
                       for f, home in zip(history["fixture"], history["was_home"])]
    history["difficulty"] = [fixtures[f]["team_h_difficulty" if home else "team_a_difficulty"]
                             for f, home in zip(history["fixture"], history["was_home"])]
    for col in ("expected_goals", "expected_assists"):
        history[col] = history[col].astype(float)

    # Team model per gameweek, fitted before that gameweek's first kickoff.
    matches = load_matches()
    teams, promoted, relegated = _league_context()
    opp_goals, opp_factor = {}, {}
    for gw in sorted(history["gameweek"].unique()):
        gw_fixtures = [f for f in fixtures.values() if f["event"] == gw]
        strengths = fit_team_strengths(matches, pd.Timestamp(min(f["kickoff_time"] for f in gw_fixtures)),
                                       teams, promoted, relegated)
        for f in gw_fixtures:
            home, away = teams_by_id[f["team_h"]], teams_by_id[f["team_a"]]
            exp_home, exp_away = strengths.expected_goals(home, away)
            opp_goals[(f["id"], home)], opp_goals[(f["id"], away)] = exp_away, exp_home
            opp_factor[(f["id"], home)] = strengths.opponent_factor(away, is_home=True)
            opp_factor[(f["id"], away)] = strengths.opponent_factor(home, is_home=False)
    keys = list(zip(history["fixture"], history["team"]))
    history["opponent_expected_goals"] = [opp_goals.get(k, np.nan) for k in keys]
    history["opponent_factor"] = [opp_factor.get(k, np.nan) for k in keys]
    return history


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from src import fetch

    scoring = fetch.get_bootstrap_static()["game_config"]["scoring"]
    history = _load_backtest_history()
    gameweeks = sorted(history["gameweek"].unique())[MIN_PRIOR_MATCHES:]
    rows = evaluate(history, gameweeks, scoring)

    print(f"\nProjected vs actual FPL points, gameweeks {gameweeks[0]}-{gameweeks[-1]} "
          f"({len(rows)} player-matches: played, with {MIN_PRIOR_MATCHES}+ earlier matches)\n")
    print(f"  {'':42} rank corr   MAE    total")
    for label, column in [("New: expected points (all parts added up)", "predicted"),
                          (f"Old: form (last {FORM_WINDOW}) + fixture difficulty", "old_formula")]:
        mae = (rows[column] - rows["actual"]).abs().mean()
        print(f"  {label:42} {_rank_corr(rows, column):.3f}   {mae:.3f}  {rows[column].sum():7.0f}")
    print(f"  {'Actual':42} {'':9} {'':6} {rows['actual'].sum():7.0f}")

    print("\nBy position (rank corr, new vs old):")
    for pos in ("GKP", "DEF", "MID", "FWD"):
        sub = rows[rows["position"] == pos]
        print(f"  {pos}: {_rank_corr(sub, 'predicted'):.3f} vs {_rank_corr(sub, 'old_formula'):.3f}   ({len(sub)} matches)")

    print("\nEach part - predicted total vs actual total (spots a part that's off):")
    for part in PARTS:
        print(f"  {part:26} {rows[f'pred_{part}'].sum():7.0f}  vs {rows[f'actual_{part}'].sum():6.0f}")
    print(f"  {'other (not modelled)':26} {0:7.0f}  vs {rows['actual_other'].sum():6.0f}")
