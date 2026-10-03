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

## Usage

Find your team ID in the URL of your FPL "Points" page
(`fantasy.premierleague.com/entry/<TEAM_ID>/event/...`), then:

```bash
# Your squad's projected points + suggested transfers
python -m src.cli --team <TEAM_ID>

# "What if" a specific transfer - player names or IDs both work
python -m src.cli --team <TEAM_ID> --out Palmer --in Saka
```

Replace `<TEAM_ID>` with your number, **without the angle brackets** - e.g.
`python -m src.cli --team 1524385`.

Player names can be the FPL display name (`B.Fernandes`), the full name
(`"Bruno Fernandes"` - use quotes when there's a space), or part of a name
(`Gibbs`). Capitals and accents don't matter. The tool always prints who it
matched, so check that line - and if a name is ambiguous, it lists the
options with their IDs.

Run `python -m src.cli --help` for all options.

## How accurate is it?

```bash
python -m src.backtest
```

Replays past gameweeks: for each match a player has played, it projects their
points using only data from before that match, then compares that to what
they actually scored. Compares the model against simple baselines. See
`DECISIONS.md` for why rank correlation is the headline metric.

## Check the data pipeline

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
source venv/bin/activate      # Mac/Linux
venv\Scripts\Activate.ps1     # Windows PowerShell
```
(Re-activates the virtual environment — you'll need this each new terminal
session. Your prompt should start with `(venv)`. If you see
`ModuleNotFoundError: No module named 'pandas'`, this step was missed.)
