# FPL Analytics Project

A personal Fantasy Premier League tool — player points projections, match
predictions, and team/transfer analysis. See `CLAUDE.md` for the full plan.

## First-time setup

```bash
# 1. Create and activate a virtual environment (keeps dependencies isolated
#    from the rest of your system)
python3 -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
```

## Try it

```bash
python src/fetch.py
```

You should see something like:

```
Season data loaded successfully.
Total players: 700+
Total teams: 20
Current gameweek: Gameweek 5 (id=5)
```

This confirms the data pipeline works end to end: it hit the live FPL API,
cached the response to `data/raw/bootstrap_static.json`, and read it back.

## Every time you come back to this project

```bash
source venv/bin/activate
```
(Re-activates the virtual environment — you'll need this each new terminal
session.)
