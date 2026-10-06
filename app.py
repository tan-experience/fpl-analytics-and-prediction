"""
app.py
------
The web version of the tool, built with Streamlit. Run it locally with:

    streamlit run app.py

...then open the address it prints (usually http://localhost:8501).

Beginner notes:
- Streamlit turns a plain Python script into a web page. Every `st.something()`
  call adds an element to the page: st.title() a heading, st.dataframe() a
  table, st.selectbox() a dropdown, and so on.
- Whenever the visitor changes anything (types a team ID, picks a player),
  Streamlit re-runs this whole script from top to bottom and redraws the page.
  That's why there's no "event handling" code here - just top-to-bottom logic.
- Like cli.py, this file only DISPLAYS things. All the actual calculation
  lives in src/ (team.py, transfers.py, models.py), so the website and the
  command line always give the same answers.
"""

import requests
import streamlit as st

from src.cli import _money
from src.features import build_player_features
from src.models import project_gameweek_points
from src.team import get_squad_projection
from src.transfers import simulate_transfer, suggest_transfers

REPO_URL = "https://github.com/tan-experience/fpl-analytics-and-prediction"

# Columns to show in the squad tables, with friendlier headings.
SQUAD_COLUMNS = {
    "web_name": "Player",
    "team": "Club",
    "position": "Pos",
    "now_cost": "Price (£m)",
    "projected_points": "Projected pts",
    "effective_points": "After captaincy",
}

st.set_page_config(page_title="FPL Analytics", page_icon="⚽", layout="centered")


def _player_label(player) -> str:
    """Dropdown label, e.g. 'Saka - Arsenal, £9.5m, proj 6.0'."""
    return (f"{player['web_name']} - {player['team']}, £{player['now_cost']}m, "
            f"proj {player['projected_points']:.1f}")


def _squad_table(squad_df):
    """Formats the squad for display, marking captain (C) and vice-captain (V)."""
    table = squad_df.copy()
    table["web_name"] = table.apply(
        lambda r: r["web_name"] + (" (C)" if r["is_captain"] else " (V)" if r["is_vice_captain"] else ""),
        axis=1,
    )
    return table[list(SQUAD_COLUMNS)].rename(columns=SQUAD_COLUMNS)


# ---------------------------------------------------------------- header
st.title("⚽ FPL Analytics")
st.write(
    "Enter your Fantasy Premier League team ID to see your squad's projected "
    "points, which players to consider transferring out, and the impact of any "
    "transfer you're thinking about - before you make it."
)
st.caption(
    f"🚧 Work in progress. Projections use a simple, transparent formula "
    f"(recent form + fixture difficulty). [Source code and how accurate it is]({REPO_URL})."
)

team_input = st.text_input(
    "Your FPL team ID",
    placeholder="e.g. 895045",
    help="Log in at fantasy.premierleague.com, open the Points tab, and look at "
         "the web address: .../entry/YOUR_TEAM_ID/event/...",
)

if not team_input:
    st.stop()  # nothing more to show until a team ID is entered

if not team_input.strip().isdigit():
    st.error("A team ID is a number - e.g. 895045. Check the web address of your Points page.")
    st.stop()

team_id = int(team_input.strip())

# ---------------------------------------------------------------- load data
try:
    with st.spinner("Fetching your squad from FPL..."):
        squad_df, gameweek = get_squad_projection(team_id)
        projections = project_gameweek_points(build_player_features())
except requests.HTTPError as e:
    if e.response is not None and e.response.status_code == 404:
        st.error(f"No FPL team found with ID {team_id}. Double-check the number.")
    else:
        st.error("The FPL website returned an error - it may be updating between "
                 "gameweeks. Try again in a few minutes.")
    st.stop()
except requests.RequestException:
    st.error("Couldn't reach the FPL website. Try again in a few minutes.")
    st.stop()

# ---------------------------------------------------------------- squad
st.header("Your squad")
starters = squad_df[squad_df["is_starting"]]
total = starters["effective_points"].sum()

st.metric("Projected points, starting XI", f"{total:.1f}")
st.caption(f"Squad as locked in for Gameweek {gameweek}, projected for each player's next fixture.")

st.subheader("Starting XI")
st.dataframe(_squad_table(starters), hide_index=True, width="stretch")
st.subheader("Bench")
st.dataframe(_squad_table(squad_df[~squad_df["is_starting"]]), hide_index=True, width="stretch")

# ---------------------------------------------------------------- suggestions
st.header("Transfer suggestions")
st.caption("Starters not expected to play, or below their position's average with a tough run of fixtures ahead.")

suggestions = suggest_transfers(team_id)
if not suggestions:
    st.success("Nothing flagged - your starters look fine on form and fixtures for now.")
for s in suggestions:
    gain = s["in_projected_points"] - s["out_projected_points"]
    st.markdown(
        f"**{s['out_name']} → {s['in_name']}** &nbsp; +{gain:.2f} pts, "
        f"cost {_money(s['cost_diff'])}  \n*Reason: {s['reason']}*"
    )

# ---------------------------------------------------------------- what-if
st.header("Try a transfer")
st.caption("Pick a player to sell; the second list shows same-position players you could buy.")

players_by_id = projections.set_index("id")

# Start the dropdowns on the top suggestion (if there is one), so the
# suggestions above and this section connect - rather than defaulting to
# whoever happens to be first in the squad list (often your captain).
top = suggestions[0] if suggestions else None

out_options = list(squad_df["id"])
out_id = st.selectbox(
    "Transfer out",
    options=out_options,
    index=out_options.index(top["out_id"]) if top else 0,
    format_func=lambda pid: _player_label(players_by_id.loc[pid]),
)
out_position = players_by_id.loc[out_id, "position"]

candidates = projections[
    (projections["position"] == out_position)
    & (~projections["id"].isin(squad_df["id"]))
].sort_values("projected_points", ascending=False)

in_options = list(candidates["id"])
suggested_in = top["in_id"] if top and top["out_id"] == out_id else None
in_id = st.selectbox(
    "Transfer in",
    options=in_options,
    index=in_options.index(suggested_in) if suggested_in in in_options else 0,
    format_func=lambda pid: _player_label(players_by_id.loc[pid]),
)

try:
    result = simulate_transfer(team_id, out_player_id=out_id, in_player_id=in_id)
except ValueError as e:
    # Expected problems, e.g. not enough money in the bank.
    st.warning(str(e))
else:
    col1, col2 = st.columns(2)
    col1.metric(
        "Starting XI projection",
        f"{result['new_starting_total']:.1f}",
        delta=f"{result['projected_gain']:+.2f} pts",
    )
    col2.metric("Left in the bank", f"£{result['remaining_bank']:.1f}m",
                delta=_money(-result["cost_diff"]))
    note = result["new_squad"].get("_note")
    if note is not None and note.notna().any():
        st.info(note.dropna().iloc[0])
    st.caption("Sell price is assumed to equal the current price; FPL's real rule can differ slightly.")

# ---------------------------------------------------------------- footer
st.divider()
st.caption(
    f"Uses the official FPL API; your squad is as of the last deadline (transfers "
    f"made since aren't visible publicly). Not affiliated with the Premier League. "
    f"[GitHub]({REPO_URL})"
)
