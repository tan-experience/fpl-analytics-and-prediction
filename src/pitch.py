"""
pitch.py
--------
Draws a lineup on a football pitch, FPL-app style: rows for GK, defenders,
midfielders and forwards, the bench underneath. Each player card shows the
name, a captain (C) / vice (V) badge, the next fixture (tinted green = easier,
red = harder, as in the Fixtures tab) and expected points.

Also checks a lineup the user picks themselves (any 11 of their 15) and
totals it - nothing is saved, everything is recalculated on each change.

Beginner note: Streamlit's tables can't draw a pitch, so this builds a small
piece of HTML (the language web pages are written in) with inline styling,
which the app displays with st.html().
"""

import html

POSITIONS = ["GKP", "DEF", "MID", "FWD"]

PITCH_CSS = """
<style>
.pitch { background: repeating-linear-gradient(180deg, #2f7d32 0 44px, #2b742e 44px 88px);
         border-radius: 12px; padding: 14px 6px; display: flex; flex-direction: column; gap: 14px; }
.row { display: flex; justify-content: center; gap: 6px; flex-wrap: nowrap; }
.card { background: #fcfcfb; color: #0b0b0b; border-radius: 8px; width: 82px; max-width: 18vw;
        padding: 5px 3px 4px; text-align: center; position: relative;
        font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; box-shadow: 0 1px 3px rgba(0,0,0,.35); }
.card .name { font-size: 12px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card .fixture { font-size: 10px; border-radius: 4px; margin: 3px 2px; padding: 1px 0; color: #0b0b0b; }
.card .pts { font-size: 13px; font-weight: 700; }
.card .badge { position: absolute; top: -7px; right: -5px; background: #0b0b0b; color: #fcfcfb;
               border-radius: 50%; width: 18px; height: 18px; font-size: 11px; line-height: 18px; font-weight: 700; }
.bench { margin-top: 10px; background: rgba(127,127,127,.15); border-radius: 12px; padding: 10px 6px; }
.bench-title { font-family: system-ui, sans-serif; font-size: 12px; opacity: .8; text-align: center; margin-bottom: 6px; }
@media (max-width: 480px) { .card .name { font-size: 10px; } .card .pts { font-size: 11px; } }
</style>
"""

# Fixture tints on a white card: green (easier) / red (harder) / light grey (average).
GOOD, BAD, NEUTRAL = (0, 131, 0), (227, 73, 72), "#ecebe6"


def _fixture_style(score) -> str:
    if score is None or abs(score) < 0.1:
        return f"background:{NEUTRAL}"
    r, g, b = GOOD if score > 0 else BAD
    return f"background:rgba({r},{g},{b},{0.15 + 0.45 * min(abs(score), 1.0):.2f})"


def check_lineup(squad, xi_ids: list, limits: dict) -> tuple:
    """
    Is this a legal FPL starting XI? Returns (True, "4-4-2") or
    (False, "plain-English reason").
    """
    if len(xi_ids) != 11:
        return False, f"Pick exactly 11 players (you have {len(xi_ids)})."
    counts = squad[squad["id"].isin(xi_ids)]["position"].value_counts().to_dict()
    if counts.get("GKP", 0) != 1:
        return False, "Your XI needs exactly 1 goalkeeper."
    names = {"DEF": "defenders", "MID": "midfielders", "FWD": "forwards"}
    for pos, word in names.items():
        low, high = limits[pos]
        if counts.get(pos, 0) < low:
            return False, f"Your XI needs at least {low} {word}."
        if counts.get(pos, 0) > high:
            return False, f"Your XI can have at most {high} {word}."
    return True, f"{counts.get('DEF', 0)}-{counts.get('MID', 0)}-{counts.get('FWD', 0)}"


def lineup_total(squad, xi_ids: list, captain_id: int) -> float:
    """Expected points for a chosen XI, with the captain's counted twice."""
    xi = squad[squad["id"].isin(xi_ids)]
    captain = squad.loc[squad["id"] == captain_id, "projected_points"]
    return float(xi["projected_points"].sum() + (captain.iloc[0] if len(captain) else 0.0))


def _card(player, captain_id, vice_id, fixtures) -> str:
    points = player["projected_points"] * (2 if player["id"] == captain_id else 1)
    label, score = fixtures.get(player["id"], ("", None))
    badge = ('<div class="badge">C</div>' if player["id"] == captain_id
             else '<div class="badge">V</div>' if player["id"] == vice_id else "")
    fixture = (f'<div class="fixture" style="{_fixture_style(score)}">{html.escape(label)}</div>'
               if label else '<div class="fixture">&nbsp;</div>')
    return (f'<div class="card">{badge}<div class="name">{html.escape(str(player["web_name"]))}</div>'
            f'{fixture}<div class="pts">{points:.1f}</div></div>')


def pitch_html(squad, xi_ids: list, captain_id: int, vice_id: int, fixtures: dict) -> str:
    """
    The pitch and bench as HTML. squad needs id, web_name, position and
    projected_points; fixtures maps player id -> (label like "LEE (H)",
    score from -1 hard to +1 easy, or None).
    """
    xi = squad[squad["id"].isin(xi_ids)]
    bench = squad[~squad["id"].isin(xi_ids)]
    rows = []
    for pos in POSITIONS:
        players = xi[xi["position"] == pos].sort_values("projected_points", ascending=False)
        cards = "".join(_card(p, captain_id, vice_id, fixtures) for _, p in players.iterrows())
        rows.append(f'<div class="row">{cards}</div>')
    # Bench in FPL order: sub keeper first, then outfielders best first.
    bench = bench.assign(_gk=(bench["position"] != "GKP").astype(int)).sort_values(
        ["_gk", "projected_points"], ascending=[True, False])
    bench_cards = "".join(_card(p, captain_id, vice_id, fixtures) for _, p in bench.iterrows())
    return (PITCH_CSS + f'<div class="pitch">{"".join(rows)}</div>'
            f'<div class="bench"><div class="bench-title">Bench</div>'
            f'<div class="row">{bench_cards}</div></div>')
