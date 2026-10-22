"""
track_record.py
---------------
How good have the app's predictions actually been? Compares predicted
points with what happened, week by week - for every player (the model's
track record) and for a manager's own lineup.

Where the predictions come from, for each finished gameweek:
- "saved at deadline": what the app actually showed just before the
  deadline, saved by the snapshot job (from GW8 on). The honest version -
  it includes the injury news known at the time.
- "rebuilt": recreated afterwards by the backtest, using only data from
  before that gameweek (no peeking) but without injury news. Used for the
  weeks before snapshots started.
Both live on the repo's `snapshots` branch (projections/ and rebuilt/), so
the website only reads small files and stays fast. Rebuilding needs every
player's match history (~450 downloads), which is why it runs in the
scheduled GitHub job, not on the website:

    python -m src.track_record --rebuild <folder>     (used by the job)
    python -m src.track_record                        (prints the record)
"""

import argparse
import io
from pathlib import Path

import pandas as pd

from src import fetch

# Gameweek 1 has no earlier matches and GW2 only one, so predictions start at GW3.
FIRST_GAMEWEEK = 3


def score_gameweek(predictions: pd.DataFrame, actual: pd.DataFrame) -> dict:
    """
    How one gameweek's predictions did, over players who actually played
    (whether someone plays is a separate question - see DECISIONS.md):
    rank correlation (did we order players right?), average error, and
    average predicted vs actual points.
    """
    both = actual.merge(predictions[["id", "projected_points"]], on="id", how="inner")
    played = both[both["minutes"] > 0]
    return {
        "players": len(played),
        "rank_corr": played["projected_points"].rank().corr(played["points"].rank()),
        "mae": (played["projected_points"] - played["points"]).abs().mean(),
        "predicted_avg": played["projected_points"].mean(),
        "actual_avg": played["points"].mean(),
    }


def squad_prediction(picks: list, predictions: pd.DataFrame) -> float:
    """What the predictions said a real lineup would score: each player's
    prediction x his multiplier (captain 2, bench 0...), like FPL's scoring."""
    by_id = dict(zip(predictions["id"], predictions["projected_points"]))
    return sum(by_id.get(p["element"], 0.0) * p["multiplier"] for p in picks)


def pick_source(saved, rebuilt) -> tuple:
    """Prefer the snapshot saved at the deadline; fall back to the rebuilt one."""
    if saved is not None:
        return saved, "saved at deadline"
    if rebuilt is not None:
        return rebuilt, "rebuilt"
    return None, None


def gameweeks_to_rebuild(events: list, already_saved: set) -> list:
    """Finished gameweeks (from FIRST_GAMEWEEK on) without a rebuilt file yet."""
    return [e["id"] for e in events
            if e["finished"] and e["id"] >= FIRST_GAMEWEEK and e["id"] not in already_saved]


def _read(text):
    return None if text is None else pd.read_csv(io.StringIO(text))


def predictions_for(gameweek: int) -> tuple:
    """(predictions table, source label) for a finished gameweek, or (None, None)."""
    return pick_source(_read(fetch.get_saved_predictions("projections", gameweek)),
                       _read(fetch.get_saved_predictions("rebuilt", gameweek)))


def actual_for(gameweek: int) -> pd.DataFrame:
    """Every player's actual points and minutes in a gameweek."""
    return pd.DataFrame([
        {"id": e["id"], "points": e["stats"]["total_points"], "minutes": e["stats"]["minutes"]}
        for e in fetch.get_event_live(gameweek)["elements"]
    ])


def finished_gameweeks() -> list:
    return [e["id"] for e in fetch.get_bootstrap_static()["events"]
            if e["finished"] and e["id"] >= FIRST_GAMEWEEK]


def model_record() -> pd.DataFrame:
    """The model's track record: one row per finished gameweek with predictions."""
    rows = []
    for gw in finished_gameweeks():
        predictions, source = predictions_for(gw)
        if predictions is None:
            continue
        rows.append({"gameweek": gw, "source": source, **score_gameweek(predictions, actual_for(gw))})
    return pd.DataFrame(rows)


def squad_record(team_id: int) -> pd.DataFrame:
    """A manager's lineup each week: what the predictions said vs what they scored."""
    history = {r["event"]: r for r in fetch.get_entry_history(team_id)["current"]}
    rows = []
    for gw in finished_gameweeks():
        predictions, source = predictions_for(gw)
        if predictions is None or gw not in history:
            continue
        picks = fetch.get_entry_picks(team_id, gw)["picks"]
        rows.append({"gameweek": gw, "source": source,
                     "predicted": squad_prediction(picks, predictions),
                     "actual": history[gw]["points"]})
    return pd.DataFrame(rows)


def rebuild(out_dir: Path) -> list:
    """
    Writes rebuilt predictions (rebuilt/gwNN.csv: id, projected_points) for
    every finished gameweek that doesn't have one yet. Returns the
    gameweeks written. Expensive (downloads every player's history), so it
    only runs when there's something new to rebuild.
    """
    from src.expected_points import _load_backtest_history, evaluate

    out_dir.mkdir(parents=True, exist_ok=True)
    already = {int(p.stem[2:]) for p in out_dir.glob("gw*.csv")}
    todo = gameweeks_to_rebuild(fetch.get_bootstrap_static()["events"], already)
    if not todo:
        return []

    scoring = fetch.get_bootstrap_static()["game_config"]["scoring"]
    history = _load_backtest_history()
    rows = evaluate(history, todo, scoring, only_played=False, min_prior=1)
    # A double gameweek has two rows per player: add them up.
    per_player = rows.groupby(["gameweek", "element"], as_index=False)["predicted"].sum()
    for gw in todo:
        week = per_player[per_player["gameweek"] == gw].rename(
            columns={"element": "id", "predicted": "projected_points"})[["id", "projected_points"]]
        week.round(4).to_csv(out_dir / f"gw{gw:02d}.csv", index=False)
    return todo


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Predicted vs actual, week by week.")
    parser.add_argument("--rebuild", metavar="FOLDER",
                        help="Write rebuilt predictions for finished gameweeks into FOLDER.")
    args = parser.parse_args()
    if args.rebuild:
        written = rebuild(Path(args.rebuild))
        print(f"Rebuilt gameweeks: {written}" if written else "Nothing new to rebuild.")
    else:
        print(model_record().round(3).to_string(index=False))
