"""Tests for the pitch view (src/pitch.py) and choosing your own XI."""

import pandas as pd
import pytest

from src.pitch import check_lineup, lineup_total, pitch_html

LIMITS = {"GKP": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}


def _squad():
    rows = [(1, "Raya", "GKP", 5.0), (2, "Backup", "GKP", 2.0)]
    rows += [(10 + i, f"Def{i}", "DEF", 4.0 - i * 0.5) for i in range(5)]
    rows += [(20 + i, f"Mid{i}", "MID", 6.0 - i) for i in range(5)]
    rows += [(30 + i, f"Fwd{i}", "FWD", 7.0 - i * 2) for i in range(3)]
    return pd.DataFrame(rows, columns=["id", "web_name", "position", "projected_points"]).assign(team="Arsenal")


def test_check_lineup_accepts_a_legal_eleven():
    squad = _squad()
    xi = [1, 10, 11, 12, 13, 20, 21, 22, 23, 30, 31]  # 4-4-2
    assert check_lineup(squad, xi, LIMITS) == (True, "4-4-2")


@pytest.mark.parametrize("ids, problem", [
    ([1, 10, 11, 12, 13, 20, 21, 22, 23, 30], "11 players"),                  # only 10
    ([1, 2, 10, 11, 12, 20, 21, 22, 23, 30, 31], "1 goalkeeper"),            # two keepers
    ([1, 10, 11, 20, 21, 22, 23, 24, 30, 31, 32], "at least 3 defenders"),   # 2 defenders
])
def test_check_lineup_explains_whats_wrong(ids, problem):
    ok, message = check_lineup(_squad(), ids, LIMITS)
    assert not ok
    assert problem in message


def test_lineup_total_counts_captain_twice():
    squad = _squad()
    xi = [1, 10, 11, 12, 13, 20, 21, 22, 23, 30, 31]
    base = squad[squad["id"].isin(xi)]["projected_points"].sum()
    assert lineup_total(squad, xi, captain_id=30) == pytest.approx(base + 7.0)


def test_pitch_has_one_card_per_player_with_badges():
    squad = _squad()
    xi = [1, 10, 11, 12, 13, 20, 21, 22, 23, 30, 31]
    html = pitch_html(squad, xi, captain_id=30, vice_id=20, fixtures={})
    assert html.count('class="card') == 15        # 11 on the pitch + 4 on the bench
    assert html.count(">C<") == 1 and html.count(">V<") == 1
    assert html.index("Raya") < html.index("Def0") < html.index("Mid0") < html.index("Fwd0")  # GK first
    assert "14.0" in html                          # captain's points shown doubled (7.0 x 2)


def test_names_are_escaped():
    squad = _squad()
    squad.loc[squad["id"] == 20, "web_name"] = "<b>Hack</b>"
    html = pitch_html(squad, [1, 10, 11, 12, 13, 20, 21, 22, 23, 30, 31], 30, 20, {})
    assert "<b>Hack</b>" not in html and "&lt;b&gt;Hack&lt;/b&gt;" in html
