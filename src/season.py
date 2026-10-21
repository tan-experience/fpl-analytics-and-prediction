"""
season.py
---------
A manager's season so far, week by week: points vs the average, rank,
where the points came from (by position, captain, bench), transfers and
chips. Feeds the web app's Season tab.

Everything comes from FPL's public data for a team ID - no login:
- entry/{id}/history/        points, ranks, transfers, bench points, chips
- bootstrap-static (events)  each gameweek's average and highest score
- entry/{id}/event/{gw}/picks/ + event/{gw}/live/   who you fielded and what
                                                   each player scored

A detail checked against FPL's official totals: the "multiplier" on each
pick already includes automatic substitutions and chips (0 = benched or
subbed off, 1 = counts, 2 = captain, 3 = triple captain; a Bench Boost sets
the bench to 1). So points = player's points x multiplier, with nothing to
re-apply - for the overall leader, every gameweek reconciles exactly.
"""

import pandas as pd

from src import fetch

CHIP_NAMES = {
    "bboost": "Bench Boost",
    "3xc": "Triple Captain",
    "wildcard": "Wildcard",
    "freehit": "Free Hit",
    "manager": "Assistant Manager",
}

POSITION_ORDER = ["GKP", "DEF", "MID", "FWD"]


def gameweek_breakdown(picks: list, live_points: dict, positions: dict) -> dict:
    """
    One gameweek's points split up. picks = FPL's picks list; live_points =
    {player id: points that gameweek}; positions = {player id: "GKP"/...}.
    Returns by_position (captain's extra points included in his position),
    total, captain_id, captain_points (his points x multiplier) and
    bench_points (points scored by players who didn't count).
    """
    by_position = {pos: 0 for pos in POSITION_ORDER}
    captain_id, captain_points, bench_points = None, 0, 0
    for pick in picks:
        points = live_points.get(pick["element"], 0)
        if pick["multiplier"] == 0:
            bench_points += points
            continue
        by_position[positions[pick["element"]]] += points * pick["multiplier"]
        if pick["is_captain"]:
            captain_id, captain_points = pick["element"], points * pick["multiplier"]
    return {
        "by_position": by_position,
        "total": sum(by_position.values()),
        "captain_id": captain_id,
        "captain_points": captain_points,
        "bench_points": bench_points,
    }


def weekly_table(history_rows: list, events: list, chips: list) -> pd.DataFrame:
    """
    One row per gameweek played: your points, FPL's average and top score,
    gameweek and overall rank, team value, transfers and hit cost, bench
    points and any chip used.
    """
    averages = {e["id"]: (e["average_entry_score"], e["highest_score"]) for e in events}
    chip_by_gw = {c["event"]: CHIP_NAMES.get(c["name"], c["name"]) for c in chips}
    rows = []
    for r in history_rows:
        gw = r["event"]
        average, highest = averages.get(gw, (None, None))
        rows.append({
            "gameweek": gw,
            "points": r["points"],
            "average": average,
            "highest": highest,
            "gw_rank": r["rank"],
            "overall_rank": r["overall_rank"],
            "total_points": r["total_points"],
            "value": r["value"] / 10,
            "bank": r["bank"] / 10,
            "transfers": r["event_transfers"],
            "hit_cost": r["event_transfers_cost"],
            "bench_points": r["points_on_bench"],
            "chip": chip_by_gw.get(gw, ""),
        })
    table = pd.DataFrame(rows)
    table["beat_average"] = table["points"] > table["average"]
    return table


def insights(table: pd.DataFrame) -> list:
    """A few plain-English takeaways from the weekly table."""
    played = len(table)
    lines = [f"You beat the average in {int(table['beat_average'].sum())} of {played} gameweeks."]
    lines.append(f"{int(table['bench_points'].sum())} points left on the bench.")
    if table["hit_cost"].sum():
        lines.append(f"-{int(table['hit_cost'].sum())} in transfer hits.")
    if "captain_points" in table:
        captain, total = int(table["captain_points"].sum()), int(table["points"].sum())
        lines.append(f"Captain picks: {captain} points ({captain / total:.0%} of your total).")
    return lines


def season_for_team(team_id: int) -> dict:
    """
    Everything the Season tab shows, for one team:
      summary     name, overall points and rank, last gameweek's points and rank, value, bank
      table       weekly_table() plus captain name/points per gameweek
      positions   long-format points by position per gameweek (for the stacked chart)
      insights    plain-English takeaways
    """
    bootstrap = fetch.get_bootstrap_static()
    history = fetch.get_entry_history(team_id)
    entry = fetch.get_entry(team_id)
    positions_by_type = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}
    positions = {p["id"]: positions_by_type[p["element_type"]] for p in bootstrap["elements"]}
    names = {p["id"]: p["web_name"] for p in bootstrap["elements"]}

    table = weekly_table(history["current"], bootstrap["events"], history["chips"])

    captains, captain_points, position_rows = [], [], []
    for gw in table["gameweek"]:
        picks = fetch.get_entry_picks(team_id, gw)["picks"]
        live = {e["id"]: e["stats"]["total_points"] for e in fetch.get_event_live(gw)["elements"]}
        breakdown = gameweek_breakdown(picks, live, positions)
        captains.append(names.get(breakdown["captain_id"], ""))
        captain_points.append(breakdown["captain_points"])
        for pos in POSITION_ORDER:
            position_rows.append({"gameweek": gw, "position": pos, "points": breakdown["by_position"][pos]})
    table["captain"] = captains
    table["captain_points"] = captain_points

    last = table.iloc[-1]
    summary = {
        "team_name": entry["name"],
        "overall_points": entry["summary_overall_points"],
        "overall_rank": entry["summary_overall_rank"],
        "last_gameweek": int(last["gameweek"]),
        "last_points": int(last["points"]),
        "last_gw_rank": int(last["gw_rank"]),
        "value": entry["last_deadline_value"] / 10,
        "bank": entry["last_deadline_bank"] / 10,
        "chips_used": [CHIP_NAMES.get(c["name"], c["name"]) for c in history["chips"]],
    }
    return {"summary": summary, "table": table, "positions": pd.DataFrame(position_rows),
            "insights": insights(table)}
