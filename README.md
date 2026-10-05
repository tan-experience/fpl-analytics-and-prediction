# FPL Analytics

[![tests](https://github.com/tan-experience/fpl-analytics-and-prediction/actions/workflows/tests.yml/badge.svg)](https://github.com/tan-experience/fpl-analytics-and-prediction/actions/workflows/tests.yml)

**Enter your Fantasy Premier League team ID → see your squad's projected
points, which players to transfer out, and the impact of any transfer
you're considering - before you make it.**

### [▶ Try it live](https://fpl-analytics-and-prediction.streamlit.app/) - no install, just your team ID

Built on the official FPL API (no login needed - your team ID is all it
takes), with a backtest that measures how accurate the projections really
are, and a [decision log](DECISIONS.md) explaining the product trade-offs
behind it.

> **Status:** work in progress, [live on the web](https://fpl-analytics-and-prediction.streamlit.app/). Projections are a
> simple baseline for now - a better model is next on the roadmap.

---

## What it does

**1. Projects your squad and flags transfers** - shown here for the overall
FPL leader's squad after Gameweek 5 (output trimmed):

```
Starting XI:
         Player Pos  Price  Proj   Eff
    Haaland (C) FWD   15.6  7.35 14.70
      Tarkowski DEF    6.2  8.45  8.45
           Hall DEF    5.3  6.65  6.65
            ...
         Palmer MID    9.7  0.00  0.00

Projected starting XI total: 52.2 points

Transfer suggestions (starters not expected to play, or underperforming + tough run):
  1. Palmer -> Groß  (+15.50 pts, cost -£3.8m) - not expected to play
```

**2. Tests a transfer idea before you commit to it** - checks it's legal
(same position, affordable) and shows the projected impact:

```
What if:
  OUT: Palmer (Cole Palmer, Chelsea, MID, £9.7m)
  IN:  Mbeumo (Bryan Mbeumo, Man Utd, MID, £7.9m)

  Starting XI projection: 52.25 -> 56.40  (+4.15 pts)
  Cost difference: -£1.8m, leaving £1.9m in the bank
```

## How good are the projections?

Measured, not assumed. The backtest replays past gameweeks, projects every
match using **only data available before it**, and compares against what
players actually scored:

| Approach | Rank correlation ↑ |
|---|---|
| **This model** (recent form + fixture difficulty) | **0.321** |
| Recent form only | 0.316 |
| Season average | 0.316 |

*882 player-matches, gameweeks 3–5 of 2026/27. Rank correlation measures
whether players were put in the right order (1 = perfect, 0 = random) -
the question FPL decisions actually depend on.*

**Honest read:** the model ranks players meaningfully better than chance,
but the fixture-difficulty adjustment adds very little over form alone.
That's the weakness the next phase targets.

## Product decisions

The reasoning behind the build lives in [DECISIONS.md](DECISIONS.md). Highlights:

- **Simple baseline before machine learning** - without a baseline, there's
  no way to show a complex model is actually better.
- **Rank correlation, not average error** - the "obvious" metric declared
  "predict 2 points for everyone" the winner. A metric has to match the
  decision the product supports.
- **Respecting a platform constraint** - FPL hides pending transfers
  deliberately; rather than work around it with stored passwords, the tool
  offers a what-if simulator instead.
- **Reordering the roadmap** for visible value sooner - and recording why.
- **Web app before a better model** - once the audience included people
  without a terminal, usability mattered more than accuracy gains; the
  riskiest assumption (FPL allowing cloud requests) was tested with a
  throwaway deploy first.

## Roadmap

- [x] Data pipeline from the official FPL API, with caching
- [x] Points projection (heuristic baseline)
- [x] Squad import, transfer suggestions, what-if simulator
- [x] Command-line interface
- [x] Backtest + automated tests in CI
- [x] Web app (Streamlit)
- [x] [Public deployment](https://fpl-analytics-and-prediction.streamlit.app/) - usable in a browser, no install
- [ ] **Match/goals prediction** (Poisson model) to replace the coarse 1–5
      fixture difficulty - target: beat 0.321 rank correlation
- [ ] Machine-learning projection, compared against the baseline

---

## Run it yourself

Tested with Python 3.12.

```bash
git clone https://github.com/tan-experience/fpl-analytics-and-prediction.git
cd fpl-analytics-and-prediction

python -m venv venv
source venv/bin/activate      # Mac/Linux
venv\Scripts\Activate.ps1     # Windows PowerShell

pip install -r requirements.txt
```

Each new terminal session, re-activate the virtual environment with the
`activate` line above - your prompt should start with `(venv)`. If you see
`ModuleNotFoundError: No module named 'pandas'`, that step was missed.

### Usage

Find your team ID in the URL of your FPL "Points" page
(`fantasy.premierleague.com/entry/<TEAM_ID>/event/...`), then:

```bash
# Your squad's projected points + suggested transfers
python -m src.cli --team <TEAM_ID>

# "What if" a specific transfer
python -m src.cli --team <TEAM_ID> --out Palmer --in "Bukayo Saka"

# How accurate are the projections?
python -m src.backtest

# The web app, in your browser (opens http://localhost:8501)
streamlit run app.py
```

Replace `<TEAM_ID>` with your number, **without the angle brackets** (e.g.
`--team 1234567`).

Player names can be the FPL display name (`B.Fernandes`), the full name
(`"Bruno Fernandes"` - quotes when there's a space), or part of a name
(`Gibbs`). Capitals and accents don't matter. The tool always prints who it
matched, and if a name is ambiguous it lists the options with their IDs.

### Tests

```bash
pytest
```

35 offline tests using small made-up player tables (no internet needed).
They run automatically on GitHub for every pull request - including checks
that the backtest never "peeks" at results it's trying to predict.

### Project structure

```
src/
  fetch.py       all FPL API calls, cached to data/raw/
  features.py    raw data -> per-player features (form, fixture difficulty)
  models.py      points projection formula
  team.py        import a squad by team ID
  transfers.py   transfer suggestions + what-if simulator
  backtest.py    accuracy measurement against past gameweeks
  cli.py         command-line interface
app.py           web app (Streamlit)
tests/           automated tests
DECISIONS.md     product decision log
```

### Known limitations

- Projections are a transparent heuristic, not a trained model (yet).
- Sell prices are assumed equal to current prices; FPL's real profit-sharing
  rule is slightly different.
- Uses your squad as of the last deadline - FPL's public API doesn't expose
  transfers you've made since.

---

Built as a learning and portfolio project, with AI pair-programming
([Claude Code](https://claude.com/claude-code)). Not affiliated with the
Premier League or Fantasy Premier League.

Licensed under the [MIT License](LICENSE).
