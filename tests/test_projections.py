"""Tests for src/projections.py - the single source of projections for the app."""

import pandas as pd

from src import projections


def _fake(monkeypatch):
    calls = {"n": 0}

    def fake_expected(gameweek=None):
        calls["n"] += 1
        return pd.DataFrame({"id": [1, 2], "gameweek": [8, 8], "matches": [1, 1],
                             "xp_appearance": [2.0, 0.0], "xp_total": [5.5, 0.0]})

    monkeypatch.setattr(projections, "build_player_features",
                        lambda: pd.DataFrame({"id": [1, 2], "web_name": ["Saka", "Palmer"]}))
    monkeypatch.setattr(projections, "project_next_gameweek", fake_expected)
    monkeypatch.setattr(projections, "_cache", {})
    return calls


def test_projected_points_is_the_expected_points_total(monkeypatch):
    _fake(monkeypatch)
    result = projections.get_projections()
    assert result.set_index("web_name")["projected_points"].to_dict() == {"Saka": 5.5, "Palmer": 0.0}


def test_results_are_cached(monkeypatch):
    calls = _fake(monkeypatch)
    projections.get_projections()
    projections.get_projections()
    assert calls["n"] == 1  # the second call reused the cached result


def test_callers_cannot_change_the_cached_copy(monkeypatch):
    _fake(monkeypatch)
    first = projections.get_projections()
    first["projected_points"] = 999
    assert projections.get_projections()["projected_points"].max() == 5.5


def test_horizon_projections_one_column_per_gameweek_and_a_total(monkeypatch):
    def fake_week(gameweek=None):
        return pd.DataFrame({"id": [1, 2], "gameweek": [gameweek] * 2, "matches": [1, 1],
                             "xp_total": [float(gameweek), 1.0]})

    monkeypatch.setattr(projections, "build_player_features",
                        lambda: pd.DataFrame({"id": [1, 2], "web_name": ["Saka", "Palmer"]}))
    monkeypatch.setattr(projections, "project_next_gameweek", fake_week)
    monkeypatch.setattr(projections, "_horizon_cache", {})
    import src.fetch as fetch
    monkeypatch.setattr(fetch, "get_bootstrap_static", lambda: {"events": [
        {"id": 7, "is_next": False}, {"id": 8, "is_next": True}, {"id": 9, "is_next": False},
        {"id": 10, "is_next": False}]})

    result = projections.get_horizon_projections(3).set_index("web_name")
    assert result.attrs["gameweeks"] == [8, 9, 10]
    assert result.loc["Saka", ["xp_gw8", "xp_gw9", "xp_gw10"]].tolist() == [8.0, 9.0, 10.0]
    assert result.loc["Saka", "xp_total"] == 27.0
    assert result.loc["Palmer", "xp_total"] == 3.0


def test_horizon_stops_at_the_last_gameweek(monkeypatch):
    monkeypatch.setattr(projections, "build_player_features", lambda: pd.DataFrame({"id": [1]}))
    monkeypatch.setattr(projections, "project_next_gameweek", lambda gameweek=None: pd.DataFrame(
        {"id": [1], "xp_total": [2.0], "matches": [1]}))
    monkeypatch.setattr(projections, "_horizon_cache", {})
    import src.fetch as fetch
    monkeypatch.setattr(fetch, "get_bootstrap_static", lambda: {"events": [
        {"id": 37, "is_next": False}, {"id": 38, "is_next": True}]})
    result = projections.get_horizon_projections(3)
    assert result.attrs["gameweeks"] == [38]  # season ends - only one week left
