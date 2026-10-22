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

import pandas as pd
import requests
import streamlit as st

from src.charts import points_chart, positions_chart, rank_chart
from src.cli import _money
from src.lineup import best_xi, formation_options
from src.fixtures import cell_colour, fixture_score, upcoming_grid
from src.free_hit import free_hit_for_team
from src.projections import get_horizon_projections, get_projections
from src.season import season_for_team
from src.team import get_squad_projection
from src.transfers import (
    plan_transfers,
    simulate_transfer,
    suggestions_from_search,
    transfer_gain_over_horizon,
    transfer_search_for_team,
)

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


@st.cache_data(ttl=600, show_spinner=False)
def _cached_search(team_id: int, horizon: int) -> dict:
    """The transfer search, kept for 10 minutes so changing other options is instant."""
    return transfer_search_for_team(team_id, horizon)


@st.cache_data(ttl=600, show_spinner=False)
def _cached_fixture_labels() -> dict:
    """{team: ["EVE (H)", "LIV (A)", ...]} for the next 3 gameweeks, for suggestion explanations."""
    grid = upcoming_grid()[0]
    return {team: list(rows.sort_values("gameweek")["label"]) for team, rows in grid.groupby("team")}


@st.cache_data(ttl=600, show_spinner=False)
def _cached_free_hit(team_id: int) -> dict:
    """The free hit squad for this team, kept for 10 minutes."""
    return free_hit_for_team(team_id)


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
# transfer?", "who has good fixtures?" and "how's my season going?".
tab_team, tab_transfers, tab_fixtures, tab_season = st.tabs(["My team", "Transfers", "Fixtures", "Season"])

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
    st.header("Transfer plan")
    col1, col2 = st.columns(2)
    horizon_label = col1.radio(
        "Judge transfers over", ["Next 3 gameweeks", "Next gameweek only"], horizontal=True,
        help="A new player keeps scoring for weeks, so judging over 3 gameweeks values "
             "transfers - and hits - more realistically. Your best XI is re-picked each week.",
    )
    horizon = 3 if horizon_label.startswith("Next 3") else 1
    free_transfers = col2.selectbox(
        "Free transfers available", options=[0, 1, 2, 3, 4, 5], index=1,
        help="Check the Transfers page in the FPL app. Each transfer beyond your free ones costs 4 points.",
    )

    # One search, used for the plan, the suggestions and the what-if defaults.
    # Cached, so changing "free transfers" doesn't re-run the whole search.
    with st.spinner("Searching every transfer and pair of transfers..."):
        search = _cached_search(team_id, horizon)
    plan = plan_transfers(search, free_transfers=free_transfers)
    options = plan["options"]
    pair = search["best_pair"]
    top_single = search["singles"].iloc[0] if len(search["singles"]) else None
    gws = search.get("gameweeks")
    period = f"over GW{gws[0]}-{gws[-1]}" if gws else "next gameweek"

    if plan["recommended"] == "none":
        st.info(f"**Recommendation: save your transfer.** No transfer improves your best XI "
                f"{period} by more than it costs.")
    elif plan["recommended"] == "single":
        st.success(f"**Recommendation: {top_single['out_name']} → {top_single['in_name']}** "
                   f"(+{options['single']['net']:.2f} pts to your best XI {period}"
                   + (f", after a -{options['single']['hit']} hit" if options["single"]["hit"] else "") + ")")
    else:
        st.success(f"**Recommendation: two transfers** - {pair['out_names'][0]} → {pair['in_names'][0]} "
                   f"and {pair['out_names'][1]} → {pair['in_names'][1]} "
                   f"(+{options['pair']['gain']:.2f} pts {period}"
                   + (f", -{options['pair']['hit']} hit = {options['pair']['net']:+.2f}" if options["pair"]["hit"] else "")
                   + f"; best formation next gameweek {pair['formation_after']})")

    if plan["hit_worth_it"] is not None:
        extra = options["pair"]["gain"] - options["single"]["gain"]
        verdict = "worth it" if plan["hit_worth_it"] else "not worth it"
        st.write(f"**Is a -4 hit worth it?** {verdict.capitalize()}: a second transfer adds "
                 f"{extra:+.2f} pts {period}, against the "
                 f"{options['pair']['hit'] - options['single']['hit']}-point cost.")

    with st.expander("Compare the options"):
        rows = [{"Plan": "No transfer", "Gain": 0.0, "Hit": 0, "Net": 0.0}]
        if top_single is not None:
            rows.append({"Plan": f"{top_single['out_name']} → {top_single['in_name']}",
                         "Gain": options["single"]["gain"], "Hit": -options["single"]["hit"],
                         "Net": options["single"]["net"]})
        if pair:
            rows.append({"Plan": f"{pair['out_names'][0]} → {pair['in_names'][0]}, "
                                 f"{pair['out_names'][1]} → {pair['in_names'][1]}",
                         "Gain": options["pair"]["gain"], "Hit": -options["pair"]["hit"],
                         "Net": options["pair"]["net"]})
        st.dataframe(pd.DataFrame(rows).round(2), hide_index=True, width="stretch")
    if horizon == 1:
        st.caption("⚠️ Next gameweek only. A new player keeps scoring for weeks, so this "
                   "undervalues transfers - hits especially. Try \"Next 3 gameweeks\".")
    else:
        st.caption(f"Judged {period}, with your best XI and captain re-picked each week. "
                   "A -4 hit is paid once.")

    st.subheader("Best single transfers")
    suggestions = suggestions_from_search(search, fixtures=_cached_fixture_labels())
    if not suggestions:
        st.write(f"No single transfer improves your best XI {period}.")
    for s in suggestions:
        st.markdown(
            f"**{s['out_name']} → {s['in_name']}** &nbsp; +{s['gain']:.2f} pts to your best XI {period}, "
            f"cost {_money(s['cost_diff'])}  \n*{s['reason']}*"
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
        horizon_gain = transfer_gain_over_horizon(team_id, out_id, in_id)
        hg = horizon_gain["gameweeks"]
        col1, col2, col3 = st.columns(3)
        col1.metric(
            f"Next gameweek: {before['formation']} → {after['formation']}",
            f"{result['new_starting_total']:.1f}",
            delta=f"{result['projected_gain']:+.2f} pts",
        )
        col2.metric(f"Over GW{hg[0]}-{hg[-1]}", f"{horizon_gain['total']:+.2f} pts",
                    help="Gain to your best XI in each week: "
                         + ", ".join(f"GW{g} {v:+.1f}" for g, v in zip(hg, horizon_gain["per_week"])))
        col3.metric("Left in the bank", f"£{result['remaining_bank']:.1f}m",
                    delta=_money(-result["cost_diff"]))
        st.caption("Compares your best possible XI (formation and captain chosen for you) "
                   "before and after the transfer - for next gameweek, and added up over "
                   "the next 3 with the lineup re-picked each week.")
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

    # ---------------------------------------------------------------- free hit
    st.header("Free Hit chip")
    st.caption("The best possible squad for next gameweek within your budget - what you'd pick "
               "with FPL's Free Hit (a one-week squad that reverts afterwards).")
    with st.spinner("Finding the best possible squad..."):
        fh = _cached_free_hit(team_id)
    if fh is None:
        st.warning("Couldn't build a legal squad within your budget.")
    else:
        fh_squad = fh["squad"]
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Free hit team ({fh['formation']})", f"{fh['total']:.1f}",
                  delta=f"{fh['gain']:+.1f} vs your best XI")
        c2.metric("Your best XI", f"{fh['current_total']:.1f}")
        c3.metric("Budget used", f"£{fh['cost']:.1f}m", help=f"Budget £{fh['budget']:.1f}m: your squad's "
                  "value at today's prices plus your bank (FPL uses selling prices, which can be a little lower).")

        # Is this a good week to use it? Free hits shine in blank/double gameweeks.
        horizon_table = get_horizon_projections()
        gws = horizon_table.attrs["gameweeks"]
        mine = horizon_table[horizon_table["id"].isin(squad_df["id"])]
        blanks = {gw: int((mine[f"matches_gw{gw}"] == 0).sum()) for gw in gws}
        doubles = {gw: int((mine[f"matches_gw{gw}"] == 2).sum()) for gw in gws}
        notes = [f"GW{gw}: {n} of your players have no match" for gw, n in blanks.items() if n]
        notes += [f"GW{gw}: {n} of your players play twice" for gw, n in doubles.items() if n]
        if notes:
            st.info("**Blank/double gameweeks ahead** - " + "; ".join(notes) + ". A free hit is usually "
                    "worth most in a week where many of your players don't play.")
        else:
            st.write(f"**Verdict:** +{fh['gain']:.1f} pts this week. None of your players have a blank or "
                     f"double gameweek in GW{gws[0]}-{gws[-1]}, so this is probably better saved for a "
                     "week when they do - the gain is usually much bigger then.")

        with st.expander(f"See the free hit team (keeps {len(fh['kept'])} of your current players)"):
            xi_view = {"xi": fh_squad[fh_squad["starting"]],
                       "captain": fh_squad.loc[fh_squad["captain"], "id"].iloc[0]}
            st.markdown(_lineup_text(xi_view))
            bench = fh_squad[~fh_squad["starting"]]
            st.caption("Bench: " + ", ".join(f"{r.web_name} ({r.position})" for r in bench.itertuples()))
            owned = set(fh["kept"])
            st.dataframe(
                fh_squad.assign(Owned=fh_squad["id"].isin(owned), Role=[
                    "Captain" if c else "Starts" if st_ else "Bench"
                    for c, st_ in zip(fh_squad["captain"], fh_squad["starting"])])
                [["web_name", "team", "position", "now_cost", "projected_points", "Role", "Owned"]]
                .rename(columns={"web_name": "Player", "team": "Club", "position": "Pos",
                                 "now_cost": "Price (£m)", "projected_points": "Expected pts"})
                .round(2),
                hide_index=True, width="stretch")

with tab_fixtures:
    # ---------------------------------------------------------------- fixtures
    mode = "light" if getattr(st.context.theme, "type", "dark") == "light" else "dark"
    try:
        with st.spinner("Rating the next few fixtures..."):
            grid, grid_gws, average_goals, average_cs = upcoming_grid()
            horizon = get_horizon_projections()
    except requests.RequestException:
        st.error("Couldn't load fixtures from FPL. Try again in a few minutes.")
    else:
        st.header(f"Next {len(grid_gws)} gameweeks")
        view = st.radio("Colour fixtures by", ["Attack: expected goals", "Defence: clean-sheet chance"],
                        horizontal=True)
        attack = view.startswith("Attack")
        value_col, average = ("xg_for", average_goals) if attack else ("clean_sheets", average_cs)

        grid["score"] = [fixture_score(v, average) if m else -1.0
                         for v, m in zip(grid[value_col], grid["matches"])]
        grid["text"] = [
            label if not m else f"{label} · {v:.1f}" if attack else f"{label} · {v:.0%}"
            for label, v, m in zip(grid["label"], grid[value_col], grid["matches"])
        ]
        # Best run of fixtures first.
        order = grid.groupby("team")["score"].sum().sort_values(ascending=False).index
        text = grid.pivot(index="team", columns="gameweek", values="text").loc[order]
        scores = grid.pivot(index="team", columns="gameweek", values="score").loc[order]
        text.columns = [f"GW{gw}" for gw in text.columns]
        text.index.name = "Club"
        scores.columns = text.columns

        styled = text.style.apply(
            lambda column: [f"background-color: {cell_colour(s_, mode)}" for s_ in scores[column.name]],
            axis=0,
        )
        st.dataframe(styled, width="stretch", height=38 * (len(text) + 1))
        st.caption(
            "**Green = easier than an average fixture, red = harder, grey = about average.** "
            + ("Numbers are the team's expected goals" if attack else "Numbers are the team's clean-sheet chance")
            + " from our team-strength model - not FPL's 1-5 difficulty rating, which barely predicts "
            "goals in our backtests. Double gameweeks show both opponents; \"—\" means no match."
        )

        st.subheader(f"Best players over the next {len(grid_gws)} gameweeks")
        col1, col2 = st.columns(2)
        position = col1.selectbox("Position", ["All", "GKP", "DEF", "MID", "FWD"])
        max_price = col2.slider("Max price (£m)", 4.0, 15.5, 15.5, step=0.5)
        shortlist = horizon[horizon["now_cost"] <= max_price]
        if position != "All":
            shortlist = shortlist[shortlist["position"] == position]
        week_cols = [f"xp_gw{gw}" for gw in horizon.attrs["gameweeks"]]
        shown = shortlist.nlargest(20, "xp_total")[
            ["web_name", "team", "position", "now_cost", *week_cols, "xp_total"]
        ].rename(columns={"web_name": "Player", "team": "Club", "position": "Pos",
                          "now_cost": "Price (£m)", "xp_total": "Total",
                          **{c: c.replace("xp_gw", "GW") for c in week_cols}})
        st.dataframe(shown.round(2), hide_index=True, width="stretch")
        st.caption("Expected points per gameweek. FPL's injury percentage only covers the next "
                   "round, but is applied to every week here, so doubtful players are cautiously "
                   "scaled down throughout.")

with tab_season:
    # ---------------------------------------------------------------- season
    try:
        with st.spinner("Loading your season..."):
            season = season_for_team(team_id)
    except requests.RequestException:
        st.error("Couldn't load your season history from FPL. Try again in a few minutes.")
    else:
        summary, weeks = season["summary"], season["table"]
        # Charts pick light or dark colours to match the viewer's theme.
        mode = "light" if getattr(st.context.theme, "type", "dark") == "light" else "dark"

        st.header(summary["team_name"])
        last = weeks.iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Overall points", f"{summary['overall_points']:,}")
        c2.metric("Overall rank", f"{summary['overall_rank']:,}")
        c3.metric(f"Gameweek {summary['last_gameweek']}", f"{summary['last_points']} pts",
                  delta=f"{summary['last_points'] - int(last['average']):+d} vs average")
        c4.metric("Team value", f"£{summary['value']:.1f}m", help=f"£{summary['bank']:.1f}m in the bank")
        st.markdown("\n".join(f"- {line}" for line in season["insights"]))
        if summary["chips_used"]:
            st.caption("Chips used: " + ", ".join(summary["chips_used"]))

        st.subheader("Am I beating the average?")
        st.altair_chart(points_chart(weeks, mode), width="stretch", theme=None)

        st.subheader("How's my rank trending?")
        st.altair_chart(rank_chart(weeks, mode), width="stretch", theme=None)

        st.subheader("Where do my points come from?")
        totals = season["positions"].groupby("position")["points"].sum()
        share = ", ".join(f"{pos} {totals[pos] / totals.sum():.0%}" for pos in ["GKP", "DEF", "MID", "FWD"])
        st.caption(f"Season so far: {share} (captain's extra points count in his position).")
        st.altair_chart(positions_chart(season["positions"], mode), width="stretch", theme=None)

        with st.expander("Gameweek by gameweek (table)"):
            show = weeks[["gameweek", "points", "average", "highest", "gw_rank", "overall_rank",
                          "captain", "captain_points", "bench_points", "transfers", "hit_cost", "chip"]]
            st.dataframe(show.rename(columns={
                "gameweek": "GW", "points": "Points", "average": "Average", "highest": "Top",
                "gw_rank": "GW rank", "overall_rank": "Overall rank", "captain": "Captain",
                "captain_points": "Captain pts", "bench_points": "Bench pts", "transfers": "Transfers",
                "hit_cost": "Hit cost", "chip": "Chip"}), hide_index=True, width="stretch")

# ---------------------------------------------------------------- footer
st.divider()
st.caption(
    f"Uses the official FPL API; your squad is as of the last deadline (transfers "
    f"made since aren't visible publicly). Not affiliated with the Premier League. "
    f"[GitHub]({REPO_URL})"
)
