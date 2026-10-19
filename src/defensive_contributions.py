"""
defensive_contributions.py
--------------------------
Phase 3, step 3: expected points from "defensive contributions".

Run it from the project root:

    python -m src.defensive_contributions

FPL's rule: +2 points in a match where a player's defensive actions reach
a threshold. Defenders count clearances, blocks, interceptions and tackles;
midfielders and forwards also count ball recoveries. The API reports the
count per match ("defensive_contribution") and the points value (2), but
not the thresholds - so these were checked against FPL's own points
breakdown for GW6: every defender on 10+ got the points and nobody on 9 or
fewer did; the same clean split at 12 for midfielders. (No forward reached
12 that week, so the forward threshold is from the published rules.)

Unlike clean sheets, this depends mostly on the PLAYER's style - a
ball-winning midfielder racks up actions whoever they play - so it's
estimated from each player's own record, not the opponent.

Two ways of estimating a player's chance of reaching the threshold, which
the backtest compares:
- "rate": their actions per 90 minutes this season, turned into a chance
  of reaching the threshold with the same Poisson maths as goals. Needs
  only FPL's main data file, so the web app stays fast.
- "history": how often they've actually reached it in past matches.
  Needs every player's match-by-match history (~700 extra API calls).
Both lean on the position's average when a player has played little.
"""

import math

import numpy as np
import pandas as pd

from src import fetch
from src.defensive_points import play_probability, team_matches_played

THRESHOLDS = {"DEF": 10, "MID": 12, "FWD": 12}  # GKPs can't earn these

# How strongly a player's estimate is pulled towards their position's
# average, in "imaginary average matches".
PRIOR_MATCHES = 3


def poisson_at_least(mean: float, threshold: int) -> float:
    """Chance a Poisson count with this average is >= threshold."""
    below = sum(math.exp(-mean) * mean ** k / math.factorial(k) for k in range(threshold))
    return max(0.0, 1.0 - below)


def hit_probability(position: str, total: float, minutes: float, position_rate: float) -> float:
    """
    "Rate" method: chance of reaching the threshold in a full match, from a
    player's season total of defensive actions and minutes played.
    position_rate = average actions per 90 for that position, used as the
    starting guess for players with little playing time.
    """
    if position not in THRESHOLDS:
        return 0.0
    matches_played = minutes / 90
    rate = (total + PRIOR_MATCHES * position_rate) / (matches_played + PRIOR_MATCHES)
    return poisson_at_least(rate, THRESHOLDS[position])


def evaluate(history: pd.DataFrame, gameweeks: list) -> pd.DataFrame:
    """
    Leakage-free backtest. For each gameweek, uses only earlier matches to
    predict each player's chance of reaching the threshold, then records
    whether they did. Only matches where the player played 60+ minutes are
    scored (whether they play is estimated separately, in play_probability).

    history columns: element, position, gameweek, minutes, defensive_contribution
    Returns one row per scored player-match with three predictions:
      p_rate:     the "rate" method
      p_history:  the "history" method (past hit rate, pulled to position average)
      p_position: just the position's average hit rate (the baseline)
    """
    history = history[history["position"].isin(THRESHOLDS)].copy()
    history["threshold"] = history["position"].map(THRESHOLDS)
    history["hit"] = (history["defensive_contribution"] >= history["threshold"]).astype(int)
    history["full"] = history["minutes"] >= 60

    rows = []
    for gw in gameweeks:
        before = history[history["gameweek"] < gw]
        this_gw = history[(history["gameweek"] == gw) & history["full"]]
        if this_gw.empty or before.empty:
            continue

        # Position averages, from earlier matches only.
        totals = before.groupby("position")[["defensive_contribution", "minutes"]].sum()
        position_rate = totals["defensive_contribution"] / (totals["minutes"] / 90)
        position_hit_rate = before[before["full"]].groupby("position")["hit"].mean()

        per_player = before.groupby("element")[["defensive_contribution", "minutes"]].sum()
        full_before = before[before["full"]].groupby("element")["hit"].agg(["sum", "count"])

        for m in this_gw.itertuples():
            pos_rate = position_rate.get(m.position, 0.0)
            pos_hit = position_hit_rate.get(m.position, 0.0)
            total, minutes = (per_player.loc[m.element] if m.element in per_player.index else (0, 0))
            hits, count = (full_before.loc[m.element] if m.element in full_before.index else (0, 0))
            rows.append({
                "gameweek": gw,
                "element": m.element,
                "position": m.position,
                "p_rate": hit_probability(m.position, total, minutes, pos_rate),
                "p_history": (hits + PRIOR_MATCHES * pos_hit) / (count + PRIOR_MATCHES),
                "p_position": pos_hit,
                "hit": m.hit,
            })
    return pd.DataFrame(rows)


def next_gameweek_contributions(gameweek: int = None) -> pd.DataFrame:
    """
    Expected defensive contribution points for every player in the next
    deadline's gameweek, using the "rate" method (FPL's main data only).
    Double gameweeks add both matches; blank gameweeks give 0.
    """
    bootstrap = fetch.get_bootstrap_static()
    fixtures = fetch.get_fixtures()
    points = bootstrap["game_config"]["scoring"]["defensive_contribution"]
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

    players = pd.DataFrame([{
        "id": p["id"], "web_name": p["web_name"], "team": teams_by_id[p["team"]],
        "position": positions[p["element_type"]], "total": p["defensive_contribution"],
        "minutes": p["minutes"], "starts": p["starts"], "status": p["status"],
        "chance": p["chance_of_playing_next_round"],
    } for p in bootstrap["elements"] if positions[p["element_type"]] in ("GKP", "DEF", "MID", "FWD")])

    by_pos = players.groupby("position")[["total", "minutes"]].sum()
    position_rate = by_pos["total"] / (by_pos["minutes"] / 90)

    def _row(p):
        p60 = play_probability(p["starts"], team_matches[p["team"]], p["status"], p["chance"])
        hit = hit_probability(p["position"], p["total"], p["minutes"], position_rate[p["position"]])
        return pd.Series({
            "p60": p60,
            "hit_chance": hit,
            "expected_dc_points": matches_this_gw[p["team"]] * p60 * hit * points[p["position"]],
        })

    return pd.concat([players, players.apply(_row, axis=1)], axis=1)


def _brier(predicted: pd.Series, hit: pd.Series) -> float:
    return float(((predicted - hit) ** 2).mean())


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    from src.backtest import _load_histories

    bootstrap = fetch.get_bootstrap_static()
    next_gw = next(e["id"] for e in bootstrap["events"] if e["is_next"])
    table = next_gameweek_contributions(next_gw)
    print(f"Gameweek {next_gw}: highest expected defensive contribution points\n")
    for pos in ("DEF", "MID", "FWD"):
        top = table[table["position"] == pos].nlargest(6, "expected_dc_points")
        print(f"{pos} (threshold {THRESHOLDS[pos]}):")
        print(top[["web_name", "team", "p60", "hit_chance", "expected_dc_points"]].round(2).to_string(index=False))
        print()

    # Backtest: compare the two methods against the position average.
    positions = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    players = [p for p in bootstrap["elements"] if p["minutes"] > 0]
    print(f"Loading match history for {len(players)} players...")
    history = pd.DataFrame(_load_histories([p["id"] for p in players]))
    history["position"] = history["element"].map({p["id"]: positions[p["element_type"]] for p in players})
    history = history.rename(columns={"round": "gameweek"})

    gameweeks = sorted(history["gameweek"].unique())[2:]  # need a couple of weeks of history first
    rows = evaluate(history, gameweeks)
    print(f"\nPredicting who reaches the threshold, gameweeks {gameweeks[0]}-{gameweeks[-1]} "
          f"({len(rows)} player-matches of 60+ minutes; {rows['hit'].sum()} reached it):")
    for label, column in [("Rate method (FPL main data only)", "p_rate"),
                          ("History method (match-by-match)", "p_history"),
                          ("Position average (baseline)", "p_position")]:
        print(f"  Brier {_brier(rows[column], rows['hit']):.3f}   expected {rows[column].sum():6.1f}   {label}")
    print("  (Brier: lower is better. 'expected' should be close to the actual count.)")
    for pos in THRESHOLDS:
        sub = rows[rows["position"] == pos]
        if len(sub):
            print(f"  {pos}: rate {_brier(sub['p_rate'], sub['hit']):.3f} | history "
                  f"{_brier(sub['p_history'], sub['hit']):.3f} | position avg "
                  f"{_brier(sub['p_position'], sub['hit']):.3f}   ({len(sub)} matches, {sub['hit'].sum()} hits)")
