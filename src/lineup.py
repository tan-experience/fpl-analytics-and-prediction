"""
lineup.py
---------
Picks the best starting XI, formation and captain from a 15-player squad.

FPL's rules (read from the API, see squad_limits()):
- exactly 1 goalkeeper starts; 3-5 defenders; 2-5 midfielders; 1-3 forwards
- 11 starters in total - which leaves exactly 8 possible formations
  (3-4-3, 3-5-2, 4-3-3, 4-4-2, 4-5-1, 5-2-3, 5-3-2, 5-4-1)
- the captain's points count twice

How it works: for each of the 8 formations, take the highest-projected
players in each position, add up their points, and keep the formation with
the best total. Checking all 8 is quick, so there's no clever maths needed.
The captain is the highest-projected starter (doubling the biggest number
adds the most).

Simplification: bench order only matters in FPL if a starter doesn't play
(automatic substitutions). We order the bench by projected points, sub
keeper first, but don't yet value the chance of a bench player coming on.
"""

from itertools import product

import pandas as pd

from src import fetch

POSITIONS = ["GKP", "DEF", "MID", "FWD"]
STARTERS = 11


def squad_limits() -> dict:
    """{position: (min starters, max starters)} from FPL's own settings."""
    return {
        p["singular_name_short"]: (p["squad_min_play"], p["squad_max_play"])
        for p in fetch.get_bootstrap_static()["element_types"]
        if p["singular_name_short"] in POSITIONS
    }


def valid_formations(limits: dict) -> list:
    """Every legal (DEF, MID, FWD) split, given FPL's per-position limits."""
    keepers = limits["GKP"][0]
    return [
        (d, m, f)
        for d, m, f in product(range(limits["DEF"][0], limits["DEF"][1] + 1),
                               range(limits["MID"][0], limits["MID"][1] + 1),
                               range(limits["FWD"][0], limits["FWD"][1] + 1))
        if keepers + d + m + f == STARTERS
    ]


def _label(formation: tuple) -> str:
    return "-".join(str(n) for n in formation)


def best_xi(squad: pd.DataFrame, limits: dict = None, formation: tuple = None) -> dict:
    """
    The best starting XI from a squad (columns: id, web_name, position,
    projected_points). If `formation` is given, e.g. (3, 5, 2), the best XI
    in that formation; otherwise the best formation overall.

    Returns a dict:
      formation             e.g. "4-4-2"
      xi, bench             DataFrames of the starters / the other four
      captain, vice_captain player ids
      total_before_captain  the XI's projected points
      total                 including the captain's points counting twice
    """
    limits = limits or squad_limits()
    # Highest projected first within each position (ties broken by id, so
    # the answer is always the same for the same squad).
    ranked = squad.sort_values(["projected_points", "id"], ascending=[False, True])
    by_position = {pos: ranked[ranked["position"] == pos] for pos in POSITIONS}

    formations = [formation] if formation else valid_formations(limits)
    best = None
    for d, m, f in formations:
        counts = {"GKP": limits["GKP"][0], "DEF": d, "MID": m, "FWD": f}
        if any(len(by_position[pos]) < n for pos, n in counts.items()):
            continue  # not enough players in some position for this formation
        xi = pd.concat([by_position[pos].head(n) for pos, n in counts.items()])
        total = xi["projected_points"].sum()
        if best is None or total > best[0] + 1e-9:
            best = (total, (d, m, f), xi)

    total, chosen, xi = best
    bench = squad[~squad["id"].isin(xi["id"])]
    # Bench order: the sub goalkeeper first (FPL's rule), then outfielders by points.
    bench = pd.concat([
        bench[bench["position"] == "GKP"],
        bench[bench["position"] != "GKP"].sort_values(["projected_points", "id"], ascending=[False, True]),
    ])
    by_points = xi.sort_values(["projected_points", "id"], ascending=[False, True])
    captain, vice = by_points["id"].iloc[0], by_points["id"].iloc[1]

    return {
        "formation": _label(chosen),
        "xi": xi.reset_index(drop=True),
        "bench": bench.reset_index(drop=True),
        "captain": captain,
        "vice_captain": vice,
        "total_before_captain": float(total),
        "total": float(total + by_points["projected_points"].iloc[0]),
    }


def formation_options(squad: pd.DataFrame, limits: dict = None) -> pd.DataFrame:
    """Every legal formation's best total (with captain), highest first."""
    limits = limits or squad_limits()
    rows = []
    for formation in valid_formations(limits):
        counts = {"DEF": formation[0], "MID": formation[1], "FWD": formation[2]}
        if all((squad["position"] == pos).sum() >= n for pos, n in counts.items()):
            result = best_xi(squad, limits, formation)
            rows.append({"formation": result["formation"], "total": result["total"]})
    return pd.DataFrame(rows).sort_values("total", ascending=False, kind="stable").reset_index(drop=True)
