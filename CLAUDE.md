# FPL Analytics Project

## What this is
A personal Fantasy Premier League (FPL) tool, built in phases:
1. Data pipeline (fetch player/team/fixture/manager data from the official FPL API)
2. Player points projection (heuristic baseline, then ML)
3. Match & goals/assists prediction (Poisson/Dixon-Coles model)
4. Team import (by manager ID), rating, and transfer suggestions
5. Simple interface (CLI first, then Streamlit)

## Who's building this
Beginner in Python. Explain new concepts simply when they come up. Prefer
small, working steps over large speculative builds. Comment code more than
you normally would.

## Folder structure
- `data/raw/` — cached raw JSON pulled from the FPL API (gitignored, regenerable)
- `data/processed/` — cleaned/derived data (gitignored, regenerable)
- `src/fetch.py` — all calls to the FPL API live here
- `src/features.py` — turns raw data into model-ready features
- `src/models.py` — projection and prediction models
- `src/team.py` — squad import, rating, transfer suggestions
- `notebooks/` — exploratory work (optional)

## Data sources
- Official FPL API — base URL `https://fantasy.premierleague.com/api/`. No auth needed.
  - `bootstrap-static/` — all players, teams, gameweeks, scoring rules
  - `fixtures/` — full fixture list with difficulty ratings
  - `entry/{team_id}/` — a manager's team info
  - `entry/{team_id}/event/{gw}/picks/` — a manager's squad for a given gameweek
  - `element-summary/{player_id}/` — one player's match-by-match history
- Underlying stats (xG/xA) beyond what FPL provides — Understat/FBref (Phase 2+, via scraping)
- Betting odds — Phase 3+, evaluate free-tier odds APIs before committing to one

## Conventions
- Python 3, virtual env in `venv/` (gitignored)
- Cache API responses to `data/raw/` rather than re-fetching every run — the
  FPL API is public but be a good citizen about request volume
- Commit at every working milestone, not just at the end
