"""
Smoke tests for the web app (app.py).

Streamlit's AppTest runs the app script without a browser, then lets us
inspect what ended up on the page. These tests only cover screens that
need no FPL data, so they stay offline like the rest of the suite.
"""

from streamlit.testing.v1 import AppTest


def test_landing_page_loads_and_waits_for_team_id():
    app = AppTest.from_file("../app.py").run()
    assert not app.exception
    assert app.title[0].value == "⚽ FPL Analytics"
    assert app.text_input[0].label == "Your FPL team ID"
    assert len(app.header) == 0  # nothing below the input until an ID is entered


def test_non_numeric_team_id_shows_friendly_error():
    app = AppTest.from_file("../app.py").run()
    app.text_input[0].input("abc").run()
    assert not app.exception
    assert "A team ID is a number" in app.error[0].value
