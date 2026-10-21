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

> **Status:** work in progress, [live on the web](https://fpl-analytics-and-prediction.streamlit.app/). Projections now
> add up every part of FPL scoring, and beat the original form-based formula
> in backtesting (see below).

---

## What it does

**1. Projects your squad's expected points** for the next gameweek - shown
here for the overall FPL leader's squad, projected for Gameweek 8 (trimmed):

```
Starting XI:
       Player Pos  Price  Proj   Eff
  Haaland (C) FWD   15.7  4.92  9.84
      Gabriel DEF    7.9  5.59  5.59
         Raya GKP    6.1  5.44  5.44
            ...

Projected starting XI total: 58.1 points
```

On the web app, each projection is broken down into the parts FPL scores -
e.g. Gabriel's 5.59 = 2.00 playing + 1.87 clean sheet + 0.60 defensive
actions + 0.83 goals/assists + 0.29 bonus - so you can see *why* a player
is rated highly. It also picks your **best XI, formation and captain**,
and shows every formation's total.

**2. Tests a transfer idea before you commit to it** - checks it's legal
(same position, affordable, max 3 per club) and compares your **best XI
before and after**, so a new signing who changes your formation is valued
properly:

```
What if:
  OUT: Slater (Regan Slater, Hull City, MID, £4.5m)
  IN:  Iwobi (Alex Iwobi, Fulham, MID, £5.4m)
  Best XI: 4-3-3 59.28 -> 3-4-3 59.87  (+0.59 pts, captain included)
  Lineup change: Iwobi starts; O'Shea drops out of the XI
  Cost difference: +£0.9m, leaving £0.2m in the bank
  Every formation after the transfer (best first):
    3-4-3  59.9
    4-3-3  59.7
    ...
```

Selling a *benched* midfielder still gains points, because the new one
starts - and the best formation changes. On the web app you can pick any
formation and see its XI.

**3. Plans your transfers over the next 3 gameweeks** - searches every single
transfer and pair of transfers (budget shared, 3-per-club limit), re-picks
your best XI each week, and tells you whether a -4 hit is worth it:

```
Transfer plan with 1 free transfer(s), over GW8-10:
  No transfer                              gain +0.00   hit -0  net +0.00
  Palmer -> Tavernier                      gain +5.63   hit -0  net +5.63
  Palmer -> Tavernier, Slater -> Mbeumo    gain +10.92  hit -4  net +6.92  <- recommended

  1. Palmer -> Tavernier (+5.63) - Tavernier 5.7 / 6.0 / 6.4 vs Palmer 4.4 / 4.1 / 4.1 (GW8-10)
```

Judged on next gameweek alone, the same hit looked *not* worth it (-0.9) -
see [DECISIONS.md](DECISIONS.md).

## How good are the projections?

Measured, not assumed. The backtest replays past gameweeks, projects every
match using **only data available before it**, and compares against what
players actually scored:

| Approach | Rank correlation ↑ | Avg miss (points) ↓ |
|---|---|---|
| **Expected points** (every scoring part added up) | **0.366** | **2.19** |
| Original formula (recent form + fixture difficulty) | 0.318 | 2.30 |

*1,469 player-matches, gameweeks 3–7 of 2026/27 - the same matches for both.
Rank correlation measures whether players were put in the right order
(1 = perfect, 0 = random) - the question FPL decisions actually depend on.*

How expected points are built, each part backtested on its own:
- **Team strength** (attack/defence ratings from last season + this season)
  predicts team goals far better than FPL's 1–5 difficulty rating (0.21 vs 0.10)
- **Clean sheets**: 31.7 predicted vs 32 actual over GW2–7
- **Defensive contributions**: from each player's actions per 90
- **Goals and assists**: from xG/xA, adjusted for the opponent - beats recent
  actual goals/assists (0.27 vs 0.22)
- **Playing time, bonus and saves**: from this season's record

**Honest read:** better for defenders, midfielders and forwards; slightly
worse for goalkeepers so far (99 matches - too few to be sure). Early-season
sample sizes, so the numbers will move as the season goes on.

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
- **Breaking the prediction into FPL's scoring parts** - a user question
  exposed that defensive contributions were invisible inside "form";
  modelling each part separately made every piece checkable.
- **Switching only on evidence** - the new model replaced the old formula
  only after beating it on the same matches; each part was backtested
  against a simpler alternative first, and several "obvious" choices lost.

## Roadmap

- [x] Data pipeline from the official FPL API, with caching
- [x] Points projection (heuristic baseline)
- [x] Squad import, transfer suggestions, what-if simulator
- [x] Command-line interface
- [x] Backtest + automated tests in CI
- [x] Web app (Streamlit)
- [x] [Public deployment](https://fpl-analytics-and-prediction.streamlit.app/) - usable in a browser, no install
- [x] **Match/goals prediction** (Poisson model) to replace the coarse 1–5
      fixture difficulty - target: beat 0.321 rank correlation
  - [x] Team attack/defence ratings and expected goals per match
        (`python -m src.team_strength`) - predicts team goals far better
        than FPL's difficulty rating (0.21 vs 0.02 rank correlation)
  - [x] Clean-sheet and goals-conceded points per player
        (`python -m src.defensive_points`) - well calibrated: 31.7 clean
        sheets predicted vs 32 actual over GW2-7
  - [x] Defensive contribution points (`python -m src.defensive_contributions`)
        - from each player's actions per 90; 163 threshold hits predicted vs
        169 actual over GW3-7
  - [x] Goal and assist points (`python -m src.attacking_points`) - from
        each player's xG/xA per 90, adjusted for the opponent; beats recent
        goals/assists (0.27 vs 0.22 rank correlation)
  - [x] Combine into expected points (`python -m src.expected_points`) -
        **beats the original formula: 0.366 vs 0.318** rank correlation
        (GW3-7, same 1,469 player-matches)
  - [x] Switch the CLI, transfer suggestions and web app to it, with a
        per-player breakdown on the web app
- [x] App tabs; team ID in the web address (`?team=...`) for bookmarkable links;
      projections saved before every deadline (to the `snapshots` branch)
- [x] **Best XI and formation** from your squad, and every formation's
      total; transfers judged by your best XI before vs after (with the
      3-per-club limit enforced)
- [x] Transfer plan: every single transfer and pair of transfers ranked by
      best-XI gain, and whether a -4 hit pays off for your free transfers
- [x] Season tab: points vs FPL's average and top score, overall rank, and
      points by position across gameweeks, with plain-English takeaways
- [x] Next 3 gameweeks: projections per gameweek and a fixture grid coloured
      by the team model (not FPL's 1-5 rating), attack and defence views
- [x] Transfer planner and -4 hit verdict over 3 gameweeks (best XI re-picked
      each week), with week-by-week explanations and fixtures
- [x] Fixture grid in green/red like the FPL app (numbers kept in every cell for
      colour-blind readers)
- [ ] Free hit team: best 15 within your real team value
- [ ] Predicted vs actual, week by week (from the saved snapshots)
- [ ] Pitch view with player cards
- [ ] Machine-learning projection, compared against the current model

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
# Your squad's projected points + this week's transfer plan
python -m src.cli --team <TEAM_ID>
python -m src.cli --team <TEAM_ID> --free-transfers 2 --horizon 3

# "What if" a specific transfer
python -m src.cli --team <TEAM_ID> --out Palmer --in "Bukayo Saka"

# How accurate are the projections? (new model vs original formula)
python -m src.expected_points

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
  team_strength.py  team attack/defence ratings, expected goals per match
  defensive_points.py  clean-sheet and goals-conceded points per player
  defensive_contributions.py  defensive contribution points per player
  attacking_points.py  goal and assist points per player
  expected_points.py  all parts combined + backtest vs the original formula
  cli.py         command-line interface
  season.py      a manager's season week by week (Season tab)
  charts.py      Season tab charts (colour-blind-safe palette, light/dark)
  fixtures.py    upcoming-fixtures grid (Fixtures tab)
app.py           web app (Streamlit)
tests/           automated tests
DECISIONS.md     product decision log
```

### Known limitations

- Projections are built from transparent, separately-tested parts rather than
  a trained machine-learning model. Small parts of FPL scoring aren't modelled
  yet: the 1 point for substitute appearances, cards, penalties and own goals.
- Transfer suggestions still flag "tough runs" using FPL's 1–5 difficulty
  over the next 3 gameweeks; projections cover the next gameweek only.
- Sell prices are assumed equal to current prices; FPL's real profit-sharing
  rule is slightly different.
- Uses your squad as of the last deadline - FPL's public API doesn't expose
  transfers you've made since.

---

Built as a learning and portfolio project, with AI pair-programming
([Claude Code](https://claude.com/claude-code)). Not affiliated with the
Premier League or Fantasy Premier League.

Licensed under the [MIT License](LICENSE).
