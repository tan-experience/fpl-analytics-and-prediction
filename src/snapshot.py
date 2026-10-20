"""
snapshot.py
-----------
Saves the projections for the upcoming gameweek to a CSV file, so later we
can compare what the app PREDICTED with what actually happened.

Why this is needed: the web app (Streamlit's free hosting) has no permanent
storage, and projections change through the week as injury news arrives.
So a scheduled GitHub Actions job (.github/workflows/snapshot.yml) runs
this every few hours and saves the result to a separate "snapshots" branch
of the repo - separate so that saving a snapshot doesn't restart the live
site, which redeploys whenever `main` changes.

Each run overwrites that gameweek's file until its deadline passes; after
that the "next" gameweek moves on, so the last copy taken before the
deadline is the one that stays - what the app was saying when it counted.

Run it by hand from the project root (saves into the given folder):

    python -m src.snapshot --out snapshots
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src import fetch

# What gets saved per player: who they are, and the projection with its parts.
COLUMNS = [
    "id", "web_name", "team", "position", "now_cost", "status", "matches",
    "xp_appearance", "xp_clean_sheet_and_conceded", "xp_defensive_contribution",
    "xp_goals_and_assists", "xp_bonus", "xp_saves", "projected_points",
]


def gameweek_to_snapshot(events: list, now: datetime):
    """
    The gameweek whose deadline is next (still in the future), or None if
    the season's deadlines have all passed. `events` is FPL's gameweek list.
    """
    upcoming = [e for e in events if pd.Timestamp(e["deadline_time"]) > now]
    if not upcoming:
        return None
    return min(upcoming, key=lambda e: pd.Timestamp(e["deadline_time"]))["id"]


def save_snapshot(out_dir: Path, now: datetime = None):
    """
    Saves projections for the next deadline's gameweek to
    out_dir/gw<NN>.csv (overwriting any earlier copy for that gameweek).
    Returns the file path, or None if there's no upcoming gameweek.
    """
    from src.projections import get_projections  # imported here: it's slow to load

    now = now or datetime.now(timezone.utc)
    gameweek = gameweek_to_snapshot(fetch.get_bootstrap_static()["events"], now)
    if gameweek is None:
        return None

    projections = get_projections(gameweek)[COLUMNS].copy()
    projections.insert(0, "gameweek", gameweek)
    projections.insert(1, "snapshot_time", now.strftime("%Y-%m-%dT%H:%M:%SZ"))

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"gw{gameweek:02d}.csv"
    projections.round(4).to_csv(path, index=False)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save the upcoming gameweek's projections.")
    parser.add_argument("--out", default="snapshots", help="Folder to save into.")
    args = parser.parse_args()

    path = save_snapshot(Path(args.out))
    print(f"Saved {path}" if path else "No upcoming gameweek - nothing to save.")
