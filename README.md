# Projection snapshots

This branch holds data, not code. The `snapshot` GitHub Actions workflow on
`main` saves the app's projections for the upcoming gameweek here every few
hours (`projections/gwNN.csv`). The last copy before each deadline is kept,
so predictions can later be compared with what actually happened.

It lives on its own branch so that saving snapshots doesn't redeploy the live
Streamlit site, which follows `main`.
