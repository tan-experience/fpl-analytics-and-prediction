"""
charts.py
---------
The Season tab's charts, drawn with Altair (a charting library that comes
with Streamlit). Display only - the numbers come from season.py.

Design choices (from a data-visualisation checklist, so the charts read
clearly for everyone):
- Colours come from a fixed, tested palette, and were run through a
  colour-blindness validator in both light and dark mode. Each position
  always gets the same colour - GKP blue, DEF orange, MID aqua, FWD yellow.
- The reference lines (FPL's average and top score) are grey, so your own
  line is the one that stands out.
- Thin 2px lines, hover tooltips on everything, a legend whenever there's
  more than one series, and one y-axis per chart (never two scales).
- Light and dark mode each get their own colour steps (not just inverted).
"""

import math

import altair as alt
import pandas as pd

from src.season import POSITION_ORDER

THEMES = {
    "light": {
        "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"],
        "ink": "#0b0b0b", "secondary": "#52514e", "muted": "#898781",
        "grid": "#e1e0d9", "axis": "#c3c2b7", "surface": "#fcfcfb",
    },
    "dark": {
        "series": ["#3987e5", "#d95926", "#199e70", "#c98500"],
        "ink": "#f0efec", "secondary": "#c3c2b7", "muted": "#898781",
        "grid": "#2c2c2a", "axis": "#383835", "surface": "#1a1a19",
    },
}

FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
HEIGHT = 260


def _style(chart: alt.Chart, theme: dict) -> alt.Chart:
    """Recessive axes and grid, system font, transparent background."""
    return (
        chart.properties(height=HEIGHT, background="transparent")
        .configure_view(stroke=None)
        .configure_axis(labelColor=theme["muted"], titleColor=theme["secondary"], gridColor=theme["grid"],
                        domainColor=theme["axis"], tickColor=theme["axis"], labelFont=FONT, titleFont=FONT,
                        labelFontSize=11, titleFontSize=12, titleFontWeight="normal")
        .configure_legend(labelColor=theme["secondary"], labelFont=FONT, orient="top", labelFontSize=12)
    )


def points_chart(table: pd.DataFrame, mode: str = "dark") -> alt.Chart:
    """Your points per gameweek against FPL's average and top score."""
    theme = THEMES[mode]
    long = table.melt(id_vars="gameweek", value_vars=["points", "average", "highest"],
                      var_name="series", value_name="score")
    long["series"] = long["series"].map({"points": "You", "average": "FPL average", "highest": "Top score"})
    order = ["You", "FPL average", "Top score"]
    color = alt.Color("series:N", sort=order, legend=alt.Legend(title=None),
                      scale=alt.Scale(domain=order, range=[theme["series"][0], theme["secondary"], theme["muted"]]))
    dash = alt.StrokeDash("series:N", sort=order, legend=None,
                          scale=alt.Scale(domain=order, range=[[1, 0], [6, 4], [2, 3]]))
    x = alt.X("gameweek:O", title="Gameweek", axis=alt.Axis(labelAngle=0))

    base = alt.Chart(long).encode(x=x)
    lines = base.mark_line(strokeWidth=2).encode(y=alt.Y("score:Q", title="Points"), color=color, strokeDash=dash)
    dots = base.mark_circle(size=64).encode(y="score:Q", color=color)

    # Hover anywhere on a gameweek: a vertical guide line + all three numbers.
    wide = table[["gameweek", "points", "average", "highest"]]
    hover = alt.selection_point(fields=["gameweek"], nearest=True, on="pointerover", empty=False)
    guide = (
        alt.Chart(wide).mark_rule(color=theme["axis"], strokeWidth=1)
        .encode(x=x, opacity=alt.condition(hover, alt.value(1), alt.value(0)),
                tooltip=[alt.Tooltip("gameweek:O", title="Gameweek"), alt.Tooltip("points:Q", title="You"),
                         alt.Tooltip("average:Q", title="FPL average"), alt.Tooltip("highest:Q", title="Top score")])
        .add_params(hover)
    )
    # Direct labels at the right-hand end of each line, so you needn't look
    # back and forth to the legend. Text stays in ink colour, not the series colour.
    last = long[long["gameweek"] == long["gameweek"].max()]
    labels = (
        alt.Chart(last).mark_text(align="left", dx=8, fontSize=11, font=FONT, color=theme["secondary"])
        .encode(x=x, y="score:Q", text="series:N")
    )
    return _style(alt.layer(lines, dots, guide, labels), theme).properties(padding={"right": 90})


def rank_chart(table: pd.DataFrame, mode: str = "dark") -> alt.Chart:
    """Overall rank over time. Flipped so up = better, and on a log scale
    because ranks run from 1 to millions (going 2M -> 1M matters as much as 20k -> 10k)."""
    theme = THEMES[mode]
    x = alt.X("gameweek:O", title="Gameweek", axis=alt.Axis(labelAngle=0))
    # Gridlines only at 1, 10, 100, 1k... - a log axis otherwise draws dozens.
    top = max(int(table["overall_rank"].max()), 10)
    ticks = [10 ** k for k in range(0, math.ceil(math.log10(top)) + 1)]
    y = alt.Y("overall_rank:Q", title="Overall rank (log scale, up = better)",
              scale=alt.Scale(type="log", reverse=True, domain=[ticks[-1], 1]),
              axis=alt.Axis(values=ticks, format="~s"))
    tooltip = [alt.Tooltip("gameweek:O", title="Gameweek"),
               alt.Tooltip("overall_rank:Q", title="Overall rank", format=","),
               alt.Tooltip("gw_rank:Q", title="Gameweek rank", format=",")]
    base = alt.Chart(table).encode(x=x, y=y, tooltip=tooltip)
    line = base.mark_line(strokeWidth=2, color=theme["series"][0])
    dots = base.mark_circle(size=64, color=theme["series"][0])
    return _style(alt.layer(line, dots), theme)


def positions_chart(positions: pd.DataFrame, mode: str = "dark") -> alt.Chart:
    """Points per gameweek, stacked by position (captain's extra points included in his position)."""
    theme = THEMES[mode]
    color = alt.Color("position:N", sort=POSITION_ORDER, legend=alt.Legend(title=None),
                      scale=alt.Scale(domain=POSITION_ORDER, range=theme["series"]))
    chart = (
        alt.Chart(positions)
        .mark_bar(stroke=theme["surface"], strokeWidth=2)  # 2px gap between stacked segments
        .encode(
            x=alt.X("gameweek:O", title="Gameweek", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("sum(points):Q", title="Points"),
            color=color,
            order=alt.Order("position_order:Q"),
            tooltip=[alt.Tooltip("gameweek:O", title="Gameweek"), alt.Tooltip("position:N", title="Position"),
                     alt.Tooltip("points:Q", title="Points")],
        )
        .transform_calculate(position_order=f"indexof({POSITION_ORDER}, datum.position)")
    )
    return _style(chart, theme)
