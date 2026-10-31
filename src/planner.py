"""
planner.py
----------
A multi-week transfer planner: over the next few gameweeks, which
transfers to make each week - including when to ROLL (save) a free
transfer, e.g. to have two ready for a blank gameweek.

How it works - the same kind of solver as the free hit (free_hit.py), but
over several weeks at once. For every player and every week it decides:
    in the squad?   bought this week?   sold this week?   starting?   captain?
...to maximise the best XI's expected points (captain twice) added up over
the weeks, minus 4 for every transfer beyond the free ones, under FPL's rules:
- the usual squad rules every week (2/5/5/3, legal formation, 3 per club,
  squad value within budget)
- free transfers: you start with what you have now; each week you get 1
  more plus any you didn't use, up to a maximum of 5 (FPL's rule)
- a transfer beyond your free ones costs 4 points

Only THIS week's decision matters: next week the plan is redone with fresh
data (and new injury news). This "plan ahead, act on this week" approach is
standard for this kind of problem.

End of the horizon: a 3-week plan sees nothing after week 3, so on its own
it would happily burn transfers at the end and place no value on saving
them. Each free transfer still in hand at the end is therefore worth
END_VALUE_PER_TRANSFER points (a judgement call - see DECISIONS.md).

Simplifications (as elsewhere): prices stay at today's values, and selling
price = current price.
"""

import pandas as pd
import pulp

UNAVAILABLE = ("i", "s", "u", "n")
POSITIONS = ["GKP", "DEF", "MID", "FWD"]

BENCH_WEIGHT = 0.1             # a bench player only scores if a starter doesn't play
END_VALUE_PER_TRANSFER = 1.0   # value of each free transfer still banked at the end
HIT_COST = 4
MAX_FREE_TRANSFERS = 5         # FPL lets you bank up to 5
CANDIDATES_PER_POSITION = 30   # unowned players considered per position (the best ones)


def _candidate_pool(players, squad_ids, weeks, per_position):
    """Owned players plus the best available unowned ones per position (keeps the solver quick)."""
    owned = players[players["id"].isin(squad_ids)]
    others = players[~players["id"].isin(squad_ids) & ~players["status"].isin(UNAVAILABLE)].copy()
    if per_position:
        others["_total"] = others[weeks].sum(axis=1)
        others = others.sort_values("_total", ascending=False).groupby("position").head(per_position)
        others = others.drop(columns="_total")
    return pd.concat([owned, others], ignore_index=True)


def _solve(pool, squad_ids, budget, weeks, free_transfers, limits, sizes, club_limit,
           bench_weight, end_value, transfers_now, allow_transfers, max_free):
    """Builds and solves the plan. Returns the PuLP variables' values, or None."""
    ids = list(pool.index)
    W = len(weeks)
    owned = {i: int(pool.at[i, "id"] in squad_ids) for i in ids}
    cost = pool["now_cost"].tolist()
    points = {(i, w): float(pool.at[i, weeks[w]]) for i in ids for w in range(W)}

    prob = pulp.LpProblem("transfer_plan", pulp.LpMaximize)
    grid = [(i, w) for i in ids for w in range(W)]
    axes = (ids, list(range(W)))  # one variable per (player, week)
    x = prob.add_variable_dict("squad", axes, cat="Binary")
    start = prob.add_variable_dict("start", axes, cat="Binary")
    cap = prob.add_variable_dict("captain", axes, cat="Binary")
    buy = prob.add_variable_dict("buy", axes, cat="Binary")
    sell = prob.add_variable_dict("sell", axes, cat="Binary")
    # ft[w]: free transfers available in week w; ft[W] = what's left after the last week.
    ft = prob.add_variable_dict("free", list(range(W + 1)), lowBound=0, upBound=max_free, cat="Integer")
    used = prob.add_variable_dict("used", list(range(W)), lowBound=0, cat="Integer")
    hits = prob.add_variable_dict("hits", list(range(W)), lowBound=0, cat="Integer")

    prob += (pulp.lpSum(points[i, w] * (start[i, w] + cap[i, w] + bench_weight * (x[i, w] - start[i, w]))
                        for i, w in grid)
             - HIT_COST * pulp.lpSum(hits[w] for w in range(W))
             + end_value * ft[W])

    prob += ft[0] == free_transfers
    for w in range(W):
        for i in ids:
            before = owned[i] if w == 0 else x[i, w - 1]
            prob += x[i, w] == before + buy[i, w] - sell[i, w]
            prob += buy[i, w] + sell[i, w] <= 1
            prob += start[i, w] <= x[i, w]
            prob += cap[i, w] <= start[i, w]
        made = pulp.lpSum(buy[i, w] for i in ids)
        prob += made == used[w] + hits[w]          # each transfer is either free or a hit
        prob += used[w] <= ft[w]
        prob += ft[w + 1] <= ft[w] - used[w] + 1     # unused ones roll over, plus 1 new...
        if not allow_transfers:
            prob += made == 0
        elif w == 0 and transfers_now is not None:
            prob += made == transfers_now
        for pos in POSITIONS:
            members = [i for i in ids if pool.at[i, "position"] == pos]
            prob += pulp.lpSum(x[i, w] for i in members) == sizes[pos]
            prob += pulp.lpSum(start[i, w] for i in members) >= limits[pos][0]
            prob += pulp.lpSum(start[i, w] for i in members) <= limits[pos][1]
        prob += pulp.lpSum(start[i, w] for i in ids) == 11
        prob += pulp.lpSum(cap[i, w] for i in ids) == 1
        for club in pool["team"].unique():
            prob += pulp.lpSum(x[i, w] for i in ids if pool.at[i, "team"] == club) <= club_limit
        prob += pulp.lpSum(cost[i] * x[i, w] for i in ids) <= budget + 1e-6
    # (...and the upBound on ft caps the bank at max_free.)

    result = prob.solve(pulp.HiGHS(msg=False))
    if result.status != pulp.LpSolveStatus.Optimal:
        return None
    value = lambda v: v.value()  # noqa: E731
    return {
        "objective": result.objective,
        "x": {k: value(v) > 0.5 for k, v in x.items()},
        "start": {k: value(v) > 0.5 for k, v in start.items()},
        "cap": {k: value(v) > 0.5 for k, v in cap.items()},
        "buy": {k: value(v) > 0.5 for k, v in buy.items()},
        "sell": {k: value(v) > 0.5 for k, v in sell.items()},
        "ft": [round(value(ft[w])) for w in range(W + 1)],
        "hits": [round(value(hits[w])) for w in range(W)],
    }


def plan_weeks(players: pd.DataFrame, squad_ids: list, bank: float, weeks: list, free_transfers: int,
               limits: dict, sizes: dict, club_limit: int, bench_weight: float = BENCH_WEIGHT,
               end_value_per_transfer: float = END_VALUE_PER_TRANSFER, transfers_now: int = None,
               max_free: int = MAX_FREE_TRANSFERS, candidates_per_position: int = None):
    """
    The best transfer plan over `weeks` (projection column names, one per
    gameweek). players needs id, web_name, team, position, now_cost, status
    and the week columns. transfers_now forces how many transfers to make
    this week (None = let the planner choose; 0 = roll).

    Returns None if no legal plan exists, otherwise:
      gain      points (after hits, incl. end value) vs making no transfers at all
      budget    total squad value allowed (current squad + bank)
      weeks     per week: transfers [(out, in) names], hits, free_transfers
                available that week, points (XI + captain), captain, squad
                ids, squad_value, club_counts
    """
    pool = _candidate_pool(players, squad_ids, weeks, candidates_per_position)
    owned_cost = pool.loc[pool["id"].isin(squad_ids), "now_cost"].sum()
    budget = round(float(owned_cost) + bank, 1)
    args = (pool, set(squad_ids), budget, weeks, free_transfers, limits, sizes, club_limit,
            bench_weight, end_value_per_transfer)

    best = _solve(*args, transfers_now, True, max_free)
    if best is None:
        return None
    baseline = _solve(*args, None, False, max_free)

    names = pool["web_name"]
    out_weeks = []
    for w, week in enumerate(weeks):
        sold = [i for i in pool.index if best["sell"][i, w]]
        bought = [i for i in pool.index if best["buy"][i, w]]
        pairs = []
        for pos in POSITIONS:  # pair each sale with a purchase in the same position
            outs = sorted((i for i in sold if pool.at[i, "position"] == pos), key=lambda i: -pool.at[i, "now_cost"])
            ins = sorted((i for i in bought if pool.at[i, "position"] == pos), key=lambda i: -pool.at[i, "now_cost"])
            pairs += [(names[o], names[n]) for o, n in zip(outs, ins)]
        in_squad = [i for i in pool.index if best["x"][i, w]]
        starters = [i for i in in_squad if best["start"][i, w]]
        captain = next(i for i in starters if best["cap"][i, w])
        out_weeks.append({
            "week": week,
            "transfers": pairs,
            "hits": best["hits"][w],
            "free_transfers": best["ft"][w],
            "points": float(sum(pool.at[i, week] for i in starters) + pool.at[captain, week]),
            "captain": names[captain],
            "squad": list(pool.loc[in_squad, "id"]),
            "squad_value": float(pool.loc[in_squad, "now_cost"].sum()),
            "club_counts": pool.loc[in_squad, "team"].value_counts(),
        })
    return {"gain": best["objective"] - baseline["objective"], "budget": budget,
            "free_transfers_left": best["ft"][len(weeks)], "weeks": out_weeks}


def plan_options_for_team(team_id: int, free_transfers: int, horizon: int = 3) -> dict:
    """
    For a real team: the best plan for each number of transfers THIS week -
    0 (roll) up to your free transfers + 1 (i.e. including one -4 hit),
    capped at 5 - each judged over the next `horizon` gameweeks.

    Returns: gameweeks, options (list of {transfers_now, gain, plan}, in
    order of transfers_now) and best (the option with the highest gain;
    ties go to fewer transfers now).
    """
    from src.free_hit import squad_sizes
    from src.lineup import squad_limits
    from src.projections import get_horizon_projections, get_projections
    from src.team import get_squad_projection
    from src.transfers import _club_limit, _get_bank

    squad_df, _ = get_squad_projection(team_id)
    if horizon == 1:
        players, weeks, gameweeks = get_projections(), ["projected_points"], None
    else:
        players = get_horizon_projections(horizon)
        gameweeks = players.attrs["gameweeks"]
        weeks = [f"xp_gw{gw}" for gw in gameweeks]

    options = []
    for k in range(0, min(free_transfers + 1, MAX_FREE_TRANSFERS) + 1):
        plan = plan_weeks(players, list(squad_df["id"]), _get_bank(team_id), weeks, free_transfers,
                          squad_limits(), squad_sizes(), _club_limit(), transfers_now=k,
                          candidates_per_position=CANDIDATES_PER_POSITION)
        if plan is not None:
            options.append({"transfers_now": k, "gain": plan["gain"], "plan": plan})
    best = max(options, key=lambda o: (round(o["gain"], 6), -o["transfers_now"]))
    return {"gameweeks": gameweeks, "options": options, "best": best}


def advice(result: dict) -> str:
    """One plain-English sentence explaining the recommendation."""
    best, options = result["best"], result["options"]
    gws = result["gameweeks"]
    period = f" over GW{gws[0]}-{gws[-1]}" if gws else ""
    if best["transfers_now"] == 0:
        using = max((o for o in options if o["transfers_now"] > 0), key=lambda o: o["gain"], default=None)
        if using is None:
            return "Roll your free transfer."
        nxt = best["plan"]["weeks"][1]["free_transfers"] if len(best["plan"]["weeks"]) > 1 else None
        later = f" - you'll have {nxt} free transfers next week" if nxt else ""
        return (f"Roll{later}. Worth {best['gain'] - using['gain']:+.1f} pts{period} compared with "
                f"the best use of transfers now.")
    roll = next(o for o in options if o["transfers_now"] == 0)
    hits = best["plan"]["weeks"][0]["hits"]
    return (f"Make {best['transfers_now']} transfer{'s' if best['transfers_now'] > 1 else ''} now"
            + (f" (including a -{4 * hits} hit)" if hits else "")
            + f". Worth {best['gain'] - roll['gain']:+.1f} pts{period} compared with rolling.")
