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
  lives in src/ (projections.py, team.py, transfers.py), so the website and the
  command line always give the same answers.
"""

import requests
import streamlit as st

from src.cli import _money
from src.lineup import best_xi, formation_options
from src.projections import get_projections
from src.team import get_squad_projection
from src.transfers import simulate_transfer, suggest_transfers

REPO_URL = "https://github.com/tan-experience/fpl-analytics-and-prediction"

# Columns to show in the squad tables, with friendlier headings.
SQUAD_COLUMNS = {
    "web_name": "Player",
    "team": "Club",
    "position": "Pos",
    "now_cost": "Price (£m)",
    "projected_points": "Expected pts",
    "effective_points": "After captaincy",
}

# The parts that make up each projection, with friendlier headings.
BREAKDOWN_COLUMNS = {
    "web_name": "Player",
    "xp_appearance": "Playing",
    "xp_clean_sheet_and_conceded": "Clean sheet",
    "xp_defensive_contribution": "Def. actions",
    "xp_goals_and_assists": "Goals + assists",
    "xp_bonus": "Bonus",
    "xp_saves": "Saves",
    "projected_points": "Total",
}

st.set_page_config(page_title="FPL Analytics", page_icon="⚽", layout="centered")


def _player_label(player) -> str:
    """Dropdown label, e.g. 'Saka - Arsenal, £9.5m, proj 6.0'."""
    return (f"{player['web_name']} - {player['team']}, £{player['now_cost']}m, "
            f"proj {player['projected_points']:.1f}")


def _lineup_text(lineup: dict) -> str:
    """One line per position for a best_xi() result, captain marked (C)."""
    lines = []
    for pos in ("GKP", "DEF", "MID", "FWD"):
        names = [
            row["web_name"] + (" (C)" if row["id"] == lineup["captain"] else "")
            for _, row in lineup["xi"][lineup["xi"]["position"] == pos].iterrows()
        ]
        lines.append(f"**{pos}:** {', '.join(names)}")
    return "  \n".join(lines)


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
    f"🚧 Work in progress. Projections add up each part of FPL scoring - playing time, "
    f"clean sheets, defensive actions, goals and assists, bonus - from each player's "
    f"underlying stats and a team-strength model. [Source code and how accurate it is]({REPO_URL})."
)

# The team ID can come from the web address (?team=895045), so a page can be
# bookmarked or shared and opens straight on that team. Nothing is stored.
team_input = st.text_input(
    "Your FPL team ID",
    value=st.query_params.get("team", ""),
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
st.query_params["team"] = str(team_id)  # keep the address in sync, for bookmarking

# ---------------------------------------------------------------- load data
try:
    with st.spinner("Fetching your squad from FPL..."):
        squad_df, gameweek = get_squad_projection(team_id)
        projections = get_projections()
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

# ---------------------------------------------------------------- tabs
# Each tab answers one question: "how's my team looking?" and "who should I
# transfer?". More tabs (fixtures, season) get added as features are built.
tab_team, tab_transfers = st.tabs(["My team", "Transfers"])

with tab_team:
    # ---------------------------------------------------------------- squad
    st.header("Your squad")
    starters = squad_df[squad_df["is_starting"]]
    total = starters["effective_points"].sum()

    best = best_xi(squad_df)
    projection_gw = int(projections["gameweek"].iloc[0])

    col1, col2 = st.columns(2)
    col1.metric("Your current lineup", f"{total:.1f}")
    col2.metric(f"Best XI from your squad ({best['formation']})", f"{best['total']:.1f}",
                delta=f"{best['total'] - total:+.1f} pts")
    st.caption(f"Squad as locked in for Gameweek {gameweek}, projected for Gameweek {projection_gw}. "
               f"Both totals include captain points.")

    current_ids = set(starters["id"])
    to_start = [n for i, n in zip(best["xi"]["id"], best["xi"]["web_name"]) if i not in current_ids]
    to_bench = [n for i, n in zip(starters["id"], starters["web_name"]) if i not in set(best["xi"]["id"])]
    best_captain = squad_df.set_index("id").loc[best["captain"], "web_name"]
    with st.expander(f"Best XI: {best['formation']}, captain {best_captain}"
                     + (f" - start {', '.join(to_start)}" if to_start else "")):
        if to_start:
            st.write(f"**Start** {', '.join(to_start)} **instead of** {', '.join(to_bench)}.")
        st.markdown(_lineup_text(best))
        st.caption("Every formation's best total (with captain) - choose for yourself:")
        st.dataframe(formation_options(squad_df).rename(columns={"formation": "Formation",
                                                                 "total": "Projected pts"}).round(1),
                     hide_index=True, width="stretch")

    st.subheader("Starting XI")
    st.dataframe(_squad_table(starters), hide_index=True, width="stretch")
    st.subheader("Bench")
    st.dataframe(_squad_table(squad_df[~squad_df["is_starting"]]), hide_index=True, width="stretch")

    with st.expander("Where do these projections come from?"):
        st.caption('Expected points from each part of FPL scoring, before captaincy. '
                   '"Playing" is the 2 points for 60+ minutes, times the chance they play that long.')
        breakdown = projections.set_index("id").loc[squad_df["id"]].reset_index()
        st.dataframe(breakdown[list(BREAKDOWN_COLUMNS)].rename(columns=BREAKDOWN_COLUMNS).round(2),
                     hide_index=True, width="stretch")

with tab_transfers:
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
        before, after = result["before"], result["after"]
        col1, col2 = st.columns(2)
        col1.metric(
            f"Best XI: {before['formation']} → {after['formation']}",
            f"{result['new_starting_total']:.1f}",
            delta=f"{result['projected_gain']:+.2f} pts",
        )
        col2.metric("Left in the bank", f"£{result['remaining_bank']:.1f}m",
                    delta=_money(-result["cost_diff"]))
        st.caption("Compares your best possible XI (formation and captain chosen for you) "
                   "before and after the transfer.")
        if result["joins_xi"] or result["leaves_xi"]:
            st.write(f"**Lineup change:** {', '.join(result['joins_xi']) or 'nobody'} starts; "
                     f"{', '.join(result['leaves_xi']) or 'nobody'} drops out of the XI.")

        # Let the user pick a formation, not just accept the best one.
        options = result["formations_after"]
        labels = [f"{f} - {t:.1f} pts" + (" (best)" if i == 0 else "")
                  for i, (f, t) in enumerate(zip(options["formation"], options["total"]))]
        chosen = st.selectbox("Formation after this transfer", options=list(range(len(labels))),
                              format_func=lambda i: labels[i])
        formation = tuple(int(n) for n in options["formation"].iloc[chosen].split("-"))
        st.markdown(_lineup_text(best_xi(result["new_squad"], formation=formation)))

        compare = players_by_id.loc[[out_id, in_id]].reset_index()
        st.dataframe(compare[list(BREAKDOWN_COLUMNS)].rename(columns=BREAKDOWN_COLUMNS).round(2),
                     hide_index=True, width="stretch")
        st.caption("Sell price is assumed to equal the current price; FPL's real rule can differ slightly.")

# ---------------------------------------------------------------- footer
st.divider()
st.caption(
    f"Uses the official FPL API; your squad is as of the last deadline (transfers "
    f"made since aren't visible publicly). Not affiliated with the Premier League. "
    f"[GitHub]({REPO_URL})"
)
