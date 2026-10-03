"""
Tests for the command line's player-name matching (src/cli.py).

Each test is a plain function whose name starts with `test_`. Inside, an
`assert` statement states what must be true - if it isn't, the test fails.
`pytest.raises(ValueError)` checks that the code correctly REFUSES bad input.
"""

import pytest

from src.cli import _money, _resolve_player


def test_full_name_with_middle_name_skipped(players):
    # FPL stores "Bruno Borges Fernandes"; people type "Bruno Fernandes".
    assert _resolve_player("Bruno Fernandes", players) == 6


def test_display_name_exact_match(players):
    assert _resolve_player("B.Fernandes", players) == 6


def test_exact_display_name_wins_over_partial_matches(players):
    # "Fernandes" is exactly Mateus's display name, so he wins even though
    # Bruno's full name also contains "Fernandes". (The CLI prints who was
    # matched, so a wrong pick is visible.)
    assert _resolve_player("Fernandes", players) == 7


def test_partial_name_and_capitals(players):
    assert _resolve_player("gibbs", players) == 10


def test_words_can_be_split_differently(players):
    # "gibbs white" (space) should still find "Gibbs-White" (hyphen).
    assert _resolve_player("gibbs white", players) == 10


def test_accents_ignored(players):
    assert _resolve_player("Joao Pedro", players) == 8


def test_number_is_used_as_id(players):
    assert _resolve_player("4", players) == 4


def test_ambiguous_name_lists_options_instead_of_guessing(players):
    with pytest.raises(ValueError) as error:
        _resolve_player("Palmer", players)
    message = str(error.value)
    assert "matches several players" in message
    assert "Cole Palmer" in message and "Carl Palmer" in message


def test_squad_preference_resolves_ambiguity(players):
    # For --out, your own squad is searched first: only Cole Palmer (id 1) is yours.
    assert _resolve_player("Palmer", players, prefer_ids={1, 3, 4}) == 1


def test_unknown_name_raises(players):
    with pytest.raises(ValueError, match="No player found"):
        _resolve_player("Zzzz", players)


def test_money_formatting():
    assert _money(-0.4) == "-£0.4m"
    assert _money(1.5) == "+£1.5m"
    assert _money(0) == "+£0.0m"
