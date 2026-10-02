"""
fetch.py
--------
Everything to do with talking to the official Fantasy Premier League (FPL)
API lives in this one file. No auth/login is needed - it's a public API.

Base URL for every endpoint: https://fantasy.premierleague.com/api/

Beginner notes:
- `requests` is a Python library for making web requests (like visiting a
  URL, but from code instead of a browser).
- The FPL API replies with JSON, which Python's `requests` library can turn
  straight into a dict/list for us with `.json()`.
- We cache (save) each response to a file in data/raw/, so re-running your
  scripts while you're developing doesn't hammer FPL's servers with repeat
  requests for data that hasn't changed.
"""

import json
import os
import time
from pathlib import Path

import requests

BASE_URL = "https://fantasy.premierleague.com/api"

# This makes data/raw/ relative to the project root, regardless of where
# you run the script from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

# How old a cached file can be before we fetch a fresh copy (in seconds).
# 3600 = 1 hour. Player prices/points update roughly hourly during gameweeks.
CACHE_MAX_AGE_SECONDS = 3600


def _cached_get(url: str, cache_key: str, max_age: int = CACHE_MAX_AGE_SECONDS) -> dict:
    """
    Fetch a URL as JSON, using a local cache file if it's fresh enough.

    cache_key becomes the filename, e.g. "bootstrap_static" ->
    data/raw/bootstrap_static.json
    """
    cache_path = RAW_DATA_DIR / f"{cache_key}.json"

    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < max_age:
            with open(cache_path, "r") as f:
                return json.load(f)

    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()  # raises an error if the request failed
    data = response.json()

    with open(cache_path, "w") as f:
        json.dump(data, f)

    return data


def get_bootstrap_static() -> dict:
    """
    The single richest endpoint: all players, all teams, all gameweeks,
    and the scoring rules. Almost everything else builds on this.
    """
    return _cached_get(f"{BASE_URL}/bootstrap-static/", "bootstrap_static")


def get_fixtures() -> list:
    """Every fixture for the season, with difficulty ratings."""
    return _cached_get(f"{BASE_URL}/fixtures/", "fixtures")


def get_player_summary(player_id: int, max_age: int = 3600 * 6) -> dict:
    """
    One player's full history: past seasons, and this season's match-by-
    match performance (minutes, goals, points, etc).

    Cached for 6 hours by default (history doesn't change mid-gameweek).
    Bulk jobs like the backtest pass a longer max_age so re-running them
    doesn't re-download hundreds of players.
    """
    return _cached_get(
        f"{BASE_URL}/element-summary/{player_id}/",
        f"player_summary_{player_id}",
        max_age=max_age,
    )


def get_entry(team_id: int) -> dict:
    """
    Basic info about a manager's team (name, overall rank, total points).
    This is how we'll pull "your team" once you give us its ID.
    """
    return _cached_get(f"{BASE_URL}/entry/{team_id}/", f"entry_{team_id}")


def get_entry_picks(team_id: int, gameweek: int) -> dict:
    """
    A manager's 15-player squad for a specific gameweek, including who's
    captain/vice-captain and who's on the bench.
    """
    return _cached_get(
        f"{BASE_URL}/entry/{team_id}/event/{gameweek}/picks/",
        f"entry_{team_id}_gw{gameweek}_picks",
    )


if __name__ == "__main__":
    # A simple manual test: run `python src/fetch.py` from the project root
    # and you should see a summary printed below.
    data = get_bootstrap_static()
    current_gw = next(e for e in data["events"] if e["is_current"])

    print(f"Season data loaded successfully.")
    print(f"Total players: {len(data['elements'])}")
    print(f"Total teams: {len(data['teams'])}")
    print(f"Current gameweek: {current_gw['name']} (id={current_gw['id']})")
