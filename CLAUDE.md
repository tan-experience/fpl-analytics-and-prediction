# FPL Analytics Project

## What this is
A Fantasy Premier League (FPL) tool, live at
https://fpl-analytics-and-prediction.streamlit.app/ (public repo:
tan-experience/fpl-analytics-and-prediction). Built in phases:
1. Data pipeline (official FPL API) — done
2. Player points projection, heuristic baseline + backtest — done (now the comparison baseline)
3. Expected points from FPL's scoring parts (team strength Poisson model,
   clean sheets, defensive contributions, goals/assists) — done, live
4. Team import (by manager ID) and transfer suggestions — done
5. Interface: CLI and Streamlit web app — done, being extended

Next up (agreed plan, in order): app tabs + team ID in URL + projection
snapshots → best-XI picker with formation options, transfers judged by
best XI before/after, and -4 hit evaluation → Season tab (rank, points,
charts across gameweeks) → 3-gameweek projections + fixture grid coloured
by our team model + better suggestion explanations → free hit team (budget
= the user's real team value) → predicted-vs-actual page → pitch view with
player cards. No login: everything comes from public data by team ID, and
nothing user-specific is saved.

## Who's building this
Beginner in Python. Explain new concepts simply when they come up. Prefer
small, working steps over large speculative builds. Comment code more than
you normally would.

This project is also a portfolio piece for a career transition into AI
Product Management, and is a public GitHub repo. When relevant, flag
product-management lessons or trade-offs worth noting (scope cuts,
sequencing, platform constraints, build-vs-simplify calls), and suggest
adding them to `DECISIONS.md` in its existing format: problem, options,
decision, why, PM lesson.

## Folder structure
- `app.py` — Streamlit web app (display only; all calculation lives in `src/`)
- `src/fetch.py` — all external data calls (FPL API, football-data.co.uk), cached to `data/raw/`
- `src/features.py` — player info table + FPL fixture difficulty
- `src/projections.py` — **the single source of projections** for the CLI, suggestions and app (cached 10 min)
- `src/expected_points.py` — combines the parts into expected points; backtest vs the original formula
- `src/team_strength.py` — team attack/defence ratings (Poisson), expected goals per match
- `src/defensive_points.py` — clean-sheet and goals-conceded points
- `src/defensive_contributions.py` — defensive contribution points
- `src/attacking_points.py` — goal and assist points
- `src/models.py` — the original form + fixture formula (kept as the backtest baseline)
- `src/backtest.py` — the original formula's backtest and shared leakage-free helpers
- `src/team.py` — import a squad by team ID
- `src/transfers.py` — transfer suggestions and the what-if simulator
- `src/cli.py` — command-line interface
- `src/snapshot.py` — saves upcoming-gameweek projections (run by `.github/workflows/snapshot.yml`)
- `tests/` — pytest suite, offline (small made-up tables, no API calls)
- `DECISIONS.md` — product decision log
- `data/raw/`, `data/processed/` — caches (gitignored, regenerable)

## Data sources
- Official FPL API — base URL `https://fantasy.premierleague.com/api/`. No auth needed.
  - `bootstrap-static/` — all players, teams, gameweeks, scoring rules (`game_config.scoring`)
  - `fixtures/` — fixture list with difficulty ratings; a match counts as played
    when `finished_provisional` is true (`finished` lags until bonus is confirmed)
  - `entry/{team_id}/` and `entry/{team_id}/history/` — a manager's info and per-gameweek history
  - `entry/{team_id}/event/{gw}/picks/` — a manager's squad for a given gameweek
  - `element-summary/{player_id}/` — one player's match-by-match history
  - `event/{gw}/live/` — every player's points that gameweek, with a per-stat breakdown
- Last season's results — football-data.co.uk CSV (team names mapped in `team_strength.py`)
- Defensive contribution thresholds (DEF 10, MID/FWD 12) aren't in the API;
  verified against FPL's GW6 points breakdown

## Conventions
- Python 3.12, virtual env in `venv/` (gitignored). On Windows PowerShell:
  `venv\Scripts\Activate.ps1`
- Cache API responses to `data/raw/` rather than re-fetching every run — the
  FPL API is public but be a good citizen about request volume
- Workflow: feature branch → PR → CI (GitHub Actions runs pytest) → merge.
  **Merging to `main` redeploys the live site** (Streamlit Community Cloud).
- Projection snapshots are committed by a scheduled workflow to the separate
  `snapshots` branch (not `main`), so they don't redeploy the site.
- Every model change is backtested leakage-free (only data from before each
  gameweek) against a simpler alternative before it ships; leakage tests are
  checked by reintroducing a leak and confirming the test fails.
- Commit at every working milestone, not just at the end
