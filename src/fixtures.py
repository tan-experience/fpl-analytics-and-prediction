"""
fixtures.py
-----------
The upcoming-fixtures grid: every team's next few opponents, coloured by
how good each fixture is - using OUR team-strength model, not FPL's 1-5
difficulty rating (the backtest showed FPL's rating barely predicts goals:
rank correlation 0.10 vs our model's 0.21).

Two views, because one fixture can be good for attackers and bad for
defenders:
- Attack:  the team's expected goals in the match
- Defence: the team's chance of keeping a clean sheet

Colour: blue = easier than an average fixture, red = harder, grey = about
average. (Not green/red like the FPL app: red vs green is the classic
colour-blindness problem, while blue vs red reads clearly for almost
everyone.) The tint gets stronger the further from average.
"""

import math

import numpy as np
import pandas as pd

from src import fetch
from src.team_strength import _league_context, fit_team_strengths, load_matches

# A fixture twice as good as average (or half) gets the strongest colour.
MAX_RATIO = 2.0

# Scores this close to average are shown plain grey.
NEUTRAL_BAND = 0.1

COLOURS = {
    "light": {"good": (42, 120, 214), "bad": (227, 73, 72), "neutral": "#f0efec"},
    "dark": {"good": (57, 135, 229), "bad": (230, 103, 103), "neutral": "#383835"},
}


def build_grid(fixtures: list, strengths, short_names: dict, gameweeks: list) -> pd.DataFrame:
    """
    One row per team per gameweek: label (e.g. "LEE (H)", "—" for no match,
    two opponents for a double gameweek), matches, xg_for and xg_against
    (summed over that week's matches) and clean_sheets (expected clean
    sheets: each match's clean-sheet chance, added up).

    fixtures: [{"event": gw, "home": team name, "away": team name}, ...]
    """
    rows = []
    for team in strengths.table.index:
        for gw in gameweeks:
            labels, xg_for, xg_against, clean_sheets = [], 0.0, 0.0, 0.0
            for f in fixtures:
                if f["event"] != gw or team not in (f["home"], f["away"]):
                    continue
                exp_home, exp_away = strengths.expected_goals(f["home"], f["away"])
                at_home = f["home"] == team
                scored, conceded = (exp_home, exp_away) if at_home else (exp_away, exp_home)
                opponent = f["away"] if at_home else f["home"]
                labels.append(f"{short_names[opponent]} ({'H' if at_home else 'A'})")
                xg_for += scored
                xg_against += conceded
                clean_sheets += math.exp(-conceded)
            rows.append({"team": team, "gameweek": gw, "label": ", ".join(labels) or "—",
                         "matches": len(labels), "xg_for": xg_for, "xg_against": xg_against,
                         "clean_sheets": clean_sheets})
    return pd.DataFrame(rows)


def fixture_score(value: float, average: float) -> float:
    """
    How good a fixture is, from -1 (very hard) to +1 (very easy): the value
    compared with an average match, on a scale where twice as good and half
    as good are equally far from 0. No match at all scores -1.
    """
    if value <= 0:
        return -1.0
    return float(np.clip(math.log(value / average) / math.log(MAX_RATIO), -1.0, 1.0))


def cell_colour(score: float, mode: str = "dark") -> str:
    """Background colour for a grid cell: blue tint (easy), red tint (hard) or neutral grey."""
    palette = COLOURS[mode]
    if abs(score) < NEUTRAL_BAND:
        return palette["neutral"]
    r, g, b = palette["good"] if score > 0 else palette["bad"]
    alpha = 0.15 + 0.55 * min(abs(score), 1.0)
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"


def upcoming_grid(weeks: int = 3) -> tuple:
    """
    The grid for the next `weeks` gameweeks from live FPL data, plus the
    baselines used for colouring: returns (grid, gameweeks, average_goals,
    average_clean_sheet).
    """
    bootstrap = fetch.get_bootstrap_static()
    next_gw = next(e["id"] for e in bootstrap["events"] if e["is_next"])
    gameweeks = [gw for gw in range(next_gw, next_gw + weeks)
                 if any(e["id"] == gw for e in bootstrap["events"])]
    names = {t["id"]: t["name"] for t in bootstrap["teams"]}
    short = {t["name"]: t["short_name"] for t in bootstrap["teams"]}

    teams, promoted, relegated = _league_context()
    strengths = fit_team_strengths(load_matches(), pd.Timestamp.now(tz="UTC"), teams, promoted, relegated)
    fixtures = [
        {"event": f["event"], "home": names[f["team_h"]], "away": names[f["team_a"]]}
        for f in fetch.get_fixtures()
        if f["event"] in gameweeks and not f["finished_provisional"]
    ]
    average_goals = (strengths.home_rate + strengths.away_rate) / 2
    return (build_grid(fixtures, strengths, short, gameweeks), gameweeks,
            average_goals, math.exp(-average_goals))
