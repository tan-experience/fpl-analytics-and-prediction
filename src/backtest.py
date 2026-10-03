"""
backtest.py
-----------
How accurate are our projections, really? This file answers that by
"replaying" past gameweeks: for each match a player has already played,
we work out what our formula WOULD have projected using only information
available before that match, then compare it to what actually happened.

Run it from the project root:

    python -m src.backtest

Beginner notes:
- "Backtesting" just means testing a prediction method on the past, where
  we already know the answers. It's the standard way to check a model
  before trusting it with future decisions.
- The key rule: when projecting a match, only use data from BEFORE that
  match. Using later data (called "leakage") would make the model look
  better than it really is - like marking a test with the answers open.
- MAE (mean absolute error) = on average, how many points off were we?
  Lower is better. A projection of 5 vs an actual 2 is an error of 3.
- Rank correlation (Spearman) = did we put players in the right ORDER?
  1.0 = perfect order, 0 = no better than random. This matters a lot for
  FPL, where decisions are "who should I pick over whom", not exact scores.

Known limitations (see DECISIONS.md):
- The FPL API doesn't keep historical injury percentages, so we only test
  matches the player actually played in (minutes > 0). That means this
  measures "how good is the projection, given the player plays" - not
  whether we correctly predicted who'd be benched or injured.
- "Form" is rebuilt from each player's last FORM_WINDOW matches. That's
  close to FPL's own definition (average points over the last 30 days)
  but not identical.
"""

import time

import pandas as pd

from src import fetch
from src.models import AVERAGE_DIFFICULTY, FIXTURE_DIFFICULTY_WEIGHT

# How many previous matches make up "form". FPL uses the last 30 days,
# which is usually about 4 matches.
FORM_WINDOW = 4

# Don't test a match unless the player had at least this many earlier
# matches - a "form" built from a single game is mostly noise.
MIN_PRIOR_MATCHES = 2

# Fixture weights to try, to see whether our guessed 0.15 is any good.
WEIGHTS_TO_TRY = [0.0, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0]

# Finished-gameweek history barely changes, so cache it for a day.
HISTORY_CACHE_SECONDS = 3600 * 24

# Pause between real (non-cached) requests, to go easy on FPL's servers.
REQUEST_DELAY_SECONDS = 0.2


def _load_histories(player_ids: list) -> list:
    """
    Downloads (or reads from cache) every player's match-by-match history
    for this season. Returns one flat list of match rows.
    """
    rows = []
    for i, player_id in enumerate(player_ids, start=1):
        cache_file = fetch.RAW_DATA_DIR / f"player_summary_{player_id}.json"
        was_cached = cache_file.exists()

        summary = fetch.get_player_summary(player_id, max_age=HISTORY_CACHE_SECONDS)
        rows.extend(summary["history"])

        if not was_cached:
            time.sleep(REQUEST_DELAY_SECONDS)
        if i % 100 == 0:
            print(f"  ...loaded {i}/{len(player_ids)} players")
    return rows


def add_before_match_features(history: pd.DataFrame) -> pd.DataFrame:
    """
    Given match rows (columns: element, kickoff_time, total_points), adds
    what we'd have known BEFORE each match:
      - form_before: average points over the previous FORM_WINDOW matches
      - season_avg_before: average points over all previous matches
      - prior_matches: how many matches the player had already played
    A player's first match has no history, so its averages are missing (NaN).

    Kept separate from the downloading code so it can be tested on a small
    hand-made table - this is the part that must never "leak" the result
    we're trying to predict.
    """
    history = history.sort_values(["element", "kickoff_time"]).reset_index(drop=True)

    # For each player, look only at earlier rows. shift(1) moves every value
    # down one row, so each match sees only the matches before it - this is
    # what prevents "leakage" of the result we're trying to predict.
    by_player = history.groupby("element")["total_points"]
    history["form_before"] = by_player.transform(
        lambda pts: pts.shift(1).rolling(FORM_WINDOW, min_periods=1).mean()
    )
    history["season_avg_before"] = by_player.transform(
        lambda pts: pts.shift(1).expanding().mean()
    )
    history["prior_matches"] = history.groupby("element").cumcount()
    return history


def build_backtest_table() -> pd.DataFrame:
    """
    Builds one row per (player, past match) with:
      - form_before: average points over the previous FORM_WINDOW matches
      - season_avg_before: average points over ALL previous matches
      - difficulty: that match's fixture difficulty for the player's team
      - actual_points: what they really scored
    Only data from before each match is used for the "before" columns.
    """
    bootstrap = fetch.get_bootstrap_static()
    fixtures = {f["id"]: f for f in fetch.get_fixtures()}
    positions_by_id = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}

    # Players who have never played this season have no matches to test.
    players = [p for p in bootstrap["elements"] if p["minutes"] > 0]
    print(f"Loading match history for {len(players)} players "
          f"(first run downloads them; later runs use the cache)...")
    history = add_before_match_features(pd.DataFrame(_load_histories([p["id"] for p in players])))

    # Difficulty from the player's own team's point of view.
    def _difficulty(row):
        fixture = fixtures[row["fixture"]]
        return fixture["team_h_difficulty"] if row["was_home"] else fixture["team_a_difficulty"]

    history["difficulty"] = history.apply(_difficulty, axis=1)

    names = {p["id"]: p["web_name"] for p in players}
    positions = {p["id"]: positions_by_id[p["element_type"]] for p in players}
    history["web_name"] = history["element"].map(names)
    history["position"] = history["element"].map(positions)
    history = history.rename(columns={"total_points": "actual_points", "round": "gameweek"})

    # Keep only testable matches: the player actually played, and had
    # enough earlier matches for "form" to mean something.
    testable = history[
        (history["minutes"] > 0) & (history["prior_matches"] >= MIN_PRIOR_MATCHES)
    ]
    return testable[[
        "element", "web_name", "position", "gameweek", "minutes",
        "form_before", "season_avg_before", "difficulty", "actual_points",
    ]].reset_index(drop=True)


def project(form: pd.Series, difficulty: pd.Series, weight: float) -> pd.Series:
    """
    Same formula as models.py (form + fixture adjustment), but with the
    fixture weight as a parameter so we can try different values.
    Playing probability is left out: we only test matches the player played.
    """
    return form + (AVERAGE_DIFFICULTY - difficulty) * weight


def score(predicted: pd.Series, table: pd.DataFrame) -> dict:
    """MAE (lower = better) and average per-gameweek rank correlation (higher = better)."""
    errors = (predicted - table["actual_points"]).abs()
    scored = table.assign(predicted=predicted)
    rank_corr_by_gw = scored.groupby("gameweek").apply(
        # Spearman = ordinary correlation of the RANKS rather than the raw
        # values. Computing it this way avoids needing the scipy library.
        # A prediction that's the same for everyone has no order at all, so
        # its rank correlation is undefined - report it as missing (NaN).
        lambda gw: (
            gw["predicted"].rank().corr(gw["actual_points"].rank())
            if gw["predicted"].nunique() > 1 else float("nan")
        ),
        include_groups=False,
    )
    return {"mae": errors.mean(), "rank_corr": rank_corr_by_gw.mean()}


def run_backtest() -> dict:
    table = build_backtest_table()

    # The contenders. Simple baselines matter: if our formula can't beat
    # "use the season average", the extra complexity isn't earning its keep.
    approaches = {
        f"Our model (form + fixture, weight {FIXTURE_DIFFICULTY_WEIGHT})":
            project(table["form_before"], table["difficulty"], FIXTURE_DIFFICULTY_WEIGHT),
        "Form only (no fixture adjustment)": table["form_before"],
        "Season average so far": table["season_avg_before"],
        "Everyone scores 2 (naive)": pd.Series(2.0, index=table.index),
    }
    # Ranked by rank correlation, our headline metric: FPL decisions are
    # "who do I pick over whom", so getting the ORDER right matters most.
    results = pd.DataFrame(
        {name: score(pred, table) for name, pred in approaches.items()}
    ).T.sort_values("rank_corr", ascending=False)

    weight_sweep = pd.DataFrame({
        w: score(project(table["form_before"], table["difficulty"], w), table)
        for w in WEIGHTS_TO_TRY
    }).T
    weight_sweep.index.name = "fixture_weight"

    # Save the row-level table so it can be explored later (e.g. in a notebook).
    out_path = fetch.PROJECT_ROOT / "data" / "processed" / "backtest_rows.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path, index=False)

    return {"table": table, "results": results, "weight_sweep": weight_sweep, "csv": out_path}


if __name__ == "__main__":
    out = run_backtest()
    table = out["table"]

    print(f"\nTested {len(table)} player-matches across gameweeks "
          f"{table['gameweek'].min()}-{table['gameweek'].max()} "
          f"(matches played, with at least {MIN_PRIOR_MATCHES} earlier matches).")
    print(f"Average actual score in these matches: {table['actual_points'].mean():.2f} points.\n")

    print("How each approach did (rank_corr: higher is better; MAE: lower is better):")
    print(out["results"].round(3).to_string())
    print(f"\nWhy 'everyone scores 2' can win on MAE: most players score 1-2 points "
          f"(median here: {table['actual_points'].median():.0f}), so always guessing the "
          f"median keeps the average error low - but it can't tell you who to pick. "
          f"That's why rank_corr is the headline metric.")

    print("\nTrying different fixture weights in our formula:")
    print(out["weight_sweep"].round(3).to_string())
    best = out["weight_sweep"]["rank_corr"].idxmax()
    print(f"\nBest rank correlation at fixture weight {best} "
          f"(current setting: {FIXTURE_DIFFICULTY_WEIGHT}).")

    print(f"\nRow-level results saved to {out['csv']}")
    print("Caution: only a few gameweeks of data so far - treat these numbers as a "
          "first read, not a verdict. Re-run as the season goes on.")
