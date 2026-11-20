"""
AMD vs. NVIDIA Stock Explorer
==================
Clean light-finance market dashboard for AMD stock historical analytics (1980–2026).
Deployable on Render via gunicorn app:server.
"""

import os
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dash import Dash, dcc, html, Input, Output, State, callback_context, no_update

# ══════════════════════════════════════════════════════════════════
# DATA LOADING & PRE-PROCESSING
# ══════════════════════════════════════════════════════════════════

CSV_FILENAME = "AMD_stock_data_1980_2026.csv"

def load_data(filename: str) -> pd.DataFrame:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, filename)
    if not os.path.exists(file_path):
        file_path = filename
    
    df = pd.read_csv(file_path)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    
    if filename != CSV_FILENAME:
        if df["Date"].isna().any():
            raise ValueError(f"{filename} contains a missing date.")
        df = df.loc[df["Date"] >= "2026-01-01"].copy().reset_index(drop=True)
        columns = ["Open", "High", "Low", "Close", "Volume"]
        for column in columns:
            df[column] = pd.to_numeric(df[column], errors="raise")
        if (
            df.empty or df["Date"].duplicated().any()
            or df[columns].isna().any().any()
            or (df[columns].abs() == float("inf")).any().any()
            or (df[columns[:4]] <= 0).any().any()
            or (df["Volume"] < 0).any()
        ):
            raise ValueError(f"{filename} must contain unique sessions with valid OHLC and volume.")
        df["Daily_Return_Pct"] = df["Close"].pct_change() * 100

    return add_direction(df)


UP_OR_FLAT = "Up or flat (Close ≥ Open)"
DOWN = "Down (Close < Open)"


def add_direction(df):
    df["Direction"] = (df["Close"] >= df["Open"]).map({
        True: UP_OR_FLAT,
        False: DOWN,
    })
    return df


def weekly_bars(df):
    return add_direction(
        df.set_index("Date").resample("W-FRI").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).dropna(subset=["Open", "Close"]).reset_index()
    )


COMPARISON_FILES = {"AMD": "AMD_2026.csv", "NVDA": "NVDA_2026.csv"}
try:
    paired_data = {ticker: load_data(filename) for ticker, filename in COMPARISON_FILES.items()}
    shared_prices = pd.concat(
        [df.set_index("Date")["Close"].rename(ticker) for ticker, df in paired_data.items()],
        axis=1,
        join="inner",
    ).sort_index()
    if shared_prices.empty:
        raise ValueError("The exports have no trading dates in common.")
    data_message = f"Shared data through {shared_prices.index[-1]:%B %d, %Y} · Yahoo Finance split-adjusted closes"
except (OSError, ValueError, KeyError) as exc:
    paired_data = {}
    shared_prices = pd.DataFrame()
    if isinstance(exc, FileNotFoundError):
        data_message = "Add AMD_2026.csv and NVDA_2026.csv to enable the comparison."
    else:
        data_message = f"Check the comparison CSVs. {exc}"

has_comparison = not shared_prices.empty
detail_data = paired_data if has_comparison else {"AMD": load_data(CSV_FILENAME)}
weekly_data = {ticker: weekly_bars(df) for ticker, df in detail_data.items()}
timeline = shared_prices.index if has_comparison else detail_data["AMD"]["Date"]
MIN_DATE = timeline.min()
MAX_DATE = timeline.max()
DEFAULT_START = max(
    MIN_DATE,
    MAX_DATE - (pd.Timedelta(days=29) if has_comparison else pd.DateOffset(years=1)),
)
TOTAL_DAYS = (MAX_DATE - MIN_DATE).days

EVENT_DATE = pd.Timestamp("2026-11-12")
BASELINE_DATE = pd.Timestamp("2026-11-11")
# Sessions strictly after the announcement, per Nasdaq's 2026 trading calendar.
# Thanksgiving is closed and the Friday early close counts as one session.
EVENT_HORIZONS = {
    "1 session": pd.Timestamp("2026-11-13"),
    "5 sessions": pd.Timestamp("2026-11-19"),
    "20 sessions": pd.Timestamp("2026-12-11"),
}
EVENT_SOURCE = "https://nvidianews.nvidia.com/news/nvidia-announces-ceo-transition"
EVENT_AVAILABLE = has_comparison and MIN_DATE <= EVENT_DATE <= MAX_DATE


def date_to_days(d: pd.Timestamp) -> int:
    return (d - MIN_DATE).days

def days_to_date(days: int) -> pd.Timestamp:
    return MIN_DATE + pd.Timedelta(days=days)

if has_comparison:
    marks = pd.date_range(MIN_DATE, MAX_DATE, freq="2MS")
    SLIDER_MARKS = {date_to_days(date): date.strftime("%b") for date in marks if date > MIN_DATE}
    SLIDER_MARKS[0] = MIN_DATE.strftime("%b %d")
    SLIDER_MARKS[TOTAL_DAYS] = MAX_DATE.strftime("%b %d")
else:
    SLIDER_MARKS = {
        date_to_days(pd.Timestamp(f"{year}-01-01")): str(year)
        for year in range(1985, 2025, 5)
    }
    SLIDER_MARKS[0] = str(MIN_DATE.year)
    SLIDER_MARKS[TOTAL_DAYS] = str(MAX_DATE.year)

PRESET_WINDOWS = {
    f"{years}y": [date_to_days(max(MIN_DATE, MAX_DATE - pd.DateOffset(years=years))), TOTAL_DAYS]
    for years in (1, 5, 10)
}
PRESET_WINDOWS["max"] = [0, TOTAL_DAYS]
if has_comparison:
    PRESET_WINDOWS["latest"] = [date_to_days(DEFAULT_START), TOTAL_DAYS]
if EVENT_AVAILABLE:
    PRESET_WINDOWS["announcement"] = [
        date_to_days(max(MIN_DATE, EVENT_DATE - pd.Timedelta(days=7))),
        date_to_days(min(MAX_DATE, EVENT_HORIZONS["20 sessions"])),
    ]


# ══════════════════════════════════════════════════════════════════
# CLEAN LIGHT FINANCE THEME TOKENS
# ══════════════════════════════════════════════════════════════════

BG_PAGE = "#f8fafc"          # Soft off-white
BG_CARD = "#ffffff"          # Crisp white
TEXT_NAVY = "#0f172a"        # Deep slate/navy primary text
TEXT_SECONDARY = "#334155"   # Navy secondary
TEXT_MUTED = "#64748b"       # Cool slate muted
BORDER_COLOR = "#e2e8f0"     # Subtle border
GRID_LINE = "#f1f5f9"        # Very soft gridline

# Stock and price-direction colors
COLOR_TEAL = "#0f766e"
COLOR_VIOLET = "#7c3aed"
TICKER_COLORS = {"AMD": COLOR_TEAL, "NVDA": COLOR_VIOLET}
TICKER_NAMES = {"AMD": "AMD", "NVDA": "NVIDIA"}
COLOR_SLATE = "#64748b"
COLOR_MEAN = "#b45309"
COLOR_ZERO = "#0f172a"       # Deep navy zero-line marker

CARD_STYLE = {
    "backgroundColor": BG_CARD,
    "borderRadius": "10px",
    "border": f"1px solid {BORDER_COLOR}",
    "padding": "18px 22px",
    "boxShadow": "0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px 0 rgba(0, 0, 0, 0.02)",
}

def apply_light_theme(fig, title: str):
    fig.update_layout(
        title=dict(text=title, font=dict(color=TEXT_NAVY, size=13, weight=600)),
        paper_bgcolor=BG_CARD,
        plot_bgcolor=BG_CARD,
        font=dict(color=TEXT_NAVY, family="'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"),
        xaxis=dict(
            gridcolor=GRID_LINE,
            zerolinecolor=BORDER_COLOR,
            linecolor=BORDER_COLOR,
            tickfont=dict(color=TEXT_MUTED, size=10),
            title_font=dict(color=TEXT_MUTED, size=11),
            showspikes=True,
            spikethickness=1,
            spikedash="dot",
            spikecolor="#94a3b8",
            spikemode="across",
        ),
        yaxis=dict(
            gridcolor=GRID_LINE,
            zerolinecolor=BORDER_COLOR,
            linecolor=BORDER_COLOR,
            tickfont=dict(color=TEXT_MUTED, size=10),
            title_font=dict(color=TEXT_MUTED, size=11),
            showspikes=True,
            spikethickness=1,
            spikedash="dot",
            spikecolor="#94a3b8",
            spikemode="across",
        ),
        margin=dict(l=15, r=15, t=42, b=15),
        hovermode="x",
        legend=dict(
            bgcolor=BG_CARD,
            font=dict(color=TEXT_NAVY, size=11),
            bordercolor=BORDER_COLOR,
            borderwidth=1,
        ),
    )
    return fig

def align_market_chart(fig, start, end, *, show_dates):
    # Both overview charts use the same date domain and plot width.
    padding = max(pd.Timedelta(days=1), (end - start) * 0.01)
    fig.update_layout(margin=dict(l=60, r=24, b=36 if show_dates else 12, autoexpand=False))
    fig.update_xaxes(
        range=[start - padding, end + padding],
        showticklabels=show_dates,
        hoverformat="%b %d, %Y",
    )


def color_key_item(label, color):
    return html.Span(
        [
            html.Span(
                className="chart-color-swatch",
                style={"backgroundColor": color},
                **{"aria-hidden": "true"},
            ),
            label,
        ],
        className="chart-color-item",
    )


def event_returns_table():
    closes = {
        ticker: df.set_index("Date")["Close"] for ticker, df in paired_data.items()
    }
    rows = []
    for label, date in EVENT_HORIZONS.items():
        values = []
        for ticker in TICKER_NAMES:
            series = closes.get(ticker)
            if series is not None and BASELINE_DATE in series.index and date in series.index:
                result = (series.at[date] / series.at[BASELINE_DATE] - 1) * 100
                values.append(html.Td(f"{result:+.2f}%"))
            else:
                values.append(html.Td("Window incomplete", className="incomplete-window"))
        rows.append(html.Tr([html.Th([label, html.Small(date.strftime("%b %d"))], scope="row"), *values]))
    return html.Table(
        [
            html.Thead(html.Tr([
                html.Th("After announcement", scope="col"),
                *[
                    html.Th(name, scope="col", style={"color": TICKER_COLORS[ticker]})
                    for ticker, name in TICKER_NAMES.items()
                ],
            ])),
            html.Tbody(rows),
        ],
        className="event-returns",
    )


# ══════════════════════════════════════════════════════════════════
# DASH APP DEFINITION & LAYOUT
# ══════════════════════════════════════════════════════════════════

app = Dash(
    __name__,
    title="AMD vs. NVIDIA Stock Explorer",
    suppress_callback_exceptions=True,
)
server = app.server

app.layout = html.Div(
    style={
        "backgroundColor": BG_PAGE,
        "minHeight": "100vh",
        "fontFamily": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "color": TEXT_NAVY,
        "padding": "24px 32px 48px",
    },
    children=[
        # ── Header ───────────────────────────────────────────────
        html.Div(
            style={"marginBottom": "20px"},
            children=[
                html.H1(
                    "AMD vs. NVIDIA Stock Explorer",
                    style={"margin": "0 0 6px 0", "fontSize": "1.65rem", "fontWeight": 700, "color": TEXT_NAVY, "letterSpacing": "-0.02em"},
                ),
            ],
        ),

        html.Section(
            style={**CARD_STYLE, "marginBottom": "20px"},
            children=[
                html.Div(
                    className="comparison-header",
                    children=[
                        html.Div([
                            html.H2("Stock performance", className="comparison-title"),
                            html.P(data_message, className="comparison-caption"),
                        ]),
                        html.Div(
                            className="comparison-views",
                            role="group",
                            **{"aria-label": "Comparison window"},
                            children=[
                                html.Button(
                                    "Nov 12 CEO announcement", id="btn-announcement", n_clicks=0,
                                    disabled=not EVENT_AVAILABLE, className="dashboard-button",
                                    **{"aria-pressed": "false"},
                                ),
                                html.Button(
                                    "Latest", id="btn-latest", n_clicks=0,
                                    disabled=not has_comparison, className="dashboard-button",
                                    title="Show the 30 calendar days ending on the latest shared session",
                                    **{"aria-pressed": "true" if has_comparison else "false"},
                                ),
                            ],
                        ),
                    ],
                ),
                dcc.Graph(id="comparison-chart", config={"displayModeBar": False}, className="comparison-graph"),
                html.Div(
                    className="event-summary",
                    children=[
                        html.H3("Stock reaction around the announcement", className="comparison-title"),
                        html.P(
                            [
                                "Nov 12, 2026 · Jensen Huang resigned. Colette Kress named interim CEO. ",
                                html.A("NVIDIA announcement", href=EVENT_SOURCE, target="_blank", rel="noopener noreferrer"),
                            ],
                            className="comparison-caption",
                        ),
                        html.P("Baseline: November 11, 2026 closing prices", className="comparison-caption"),
                        event_returns_table(),
                    ],
                ),
            ],
        ),

        # ── 2. Controls Card: Segmented Control & Shared Slider ───
        html.Div(
            style={**CARD_STYLE, "marginBottom": "20px"},
            children=[
                # Top Row: Label & Segmented Presets Control
                html.Div(
                    style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "flexWrap": "wrap", "gap": "12px", "marginBottom": "12px"},
                    children=[
                        html.Div([
                            html.Span("🗓️  Time Horizon & Date Filter", style={"fontWeight": 700, "fontSize": "0.85rem", "color": TEXT_NAVY}),
                            html.Span(" — updates all charts and metric cards", style={"fontSize": "0.78rem", "color": TEXT_MUTED}),
                        ]),
                        # Segmented Control Container
                        html.Div(
                            style={
                                "display": "inline-flex",
                                "alignItems": "center",
                                "backgroundColor": "#f1f5f9",
                                "padding": "3px",
                                "gap": "3px",
                                "borderRadius": "10px",
                                "border": "1px solid #e2e8f0",
                            },
                            children=[
                                html.Button("1Y", id="btn-1y", n_clicks=0, className="dashboard-button preset-button", hidden=has_comparison),
                                html.Button("5Y", id="btn-5y", n_clicks=0, className="dashboard-button preset-button", hidden=has_comparison),
                                html.Button("10Y", id="btn-10y", n_clicks=0, className="dashboard-button preset-button", hidden=has_comparison),
                                html.Button("Max", id="btn-max", n_clicks=0, className="dashboard-button preset-button"),
                            ],
                        ),
                    ],
                ),

                # Selected Date Range displayed on its own line
                html.Div(
                    style={"marginBottom": "8px", "padding": "6px 12px", "backgroundColor": "#f1f5f9", "borderRadius": "6px", "display": "inline-block"},
                    children=[
                        html.Span("Selected Date Range: ", style={"fontSize": "0.75rem", "color": TEXT_MUTED, "fontWeight": 600, "textTransform": "uppercase"}),
                        html.Span(id="slider-range-label", style={"fontSize": "0.85rem", "fontWeight": 700, "color": TEXT_NAVY}),
                    ],
                ),

                # Clean Range Slider without white numeric input boxes
                html.Div(
                    style={"padding": "12px 10px 6px 10px"},
                    children=[
                        dcc.RangeSlider(
                            id="date-slider",
                            min=0,
                            max=TOTAL_DAYS,
                            value=[date_to_days(DEFAULT_START), TOTAL_DAYS],
                            marks=SLIDER_MARKS,
                            step=1,
                            allowCross=False,
                            tooltip={"placement": "bottom", "always_visible": False},
                        ),
                    ],
                ),
            ],
        ),

        html.Div(
            className="detail-selector",
            children=[
                html.Label("Stock detail", htmlFor="detail-stock"),
                dcc.RadioItems(
                    id="detail-stock",
                    options=[
                        {"label": html.Span("AMD", style={"color": COLOR_TEAL}), "value": "AMD"},
                        {"label": html.Span("NVIDIA", style={"color": COLOR_VIOLET}), "value": "NVDA", "disabled": not has_comparison},
                    ],
                    value="AMD",
                    inline=True,
                ),
            ],
        ),
        # ── 1. Four Headline Metric Cards (Top Row) ───────────────
        html.Div(
            id="kpi-tiles",
            style={
                "display": "grid",
                "gridTemplateColumns": "repeat(4, 1fr)",
                "gap": "16px",
                "marginBottom": "20px",
            },
        ),

        # ── 3. Overview Container: Candlestick + Volume Stacked ───
        html.Div(
            style={**CARD_STYLE, "marginBottom": "20px"},
            children=[
                # Header for Candlestick + Reset Zoom Button right next to title
                html.Div(
                    style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "6px"},
                    children=[
                        html.Div(
                            style={"display": "flex", "alignItems": "center", "gap": "10px"},
                            children=[
                                html.Div(id="candlestick-mode-badge", style={"fontSize": "0.84rem", "fontWeight": 700, "color": TEXT_NAVY}),
                                html.Button(
                                    "↺ Reset Zoom",
                                    id="btn-reset-zoom",
                                    className="dashboard-button reset-button",
                                ),
                            ],
                        ),
                        html.Div(id="zoom-status-badge", style={"fontSize": "0.76rem", "fontWeight": 600, "color": TEXT_MUTED}),
                    ],
                ),
                html.Div(id="candlestick-key", className="chart-color-key"),
                # Candlestick Chart
                dcc.Graph(
                    id="candlestick-chart",
                    config={"displayModeBar": True, "scrollZoom": True},
                    style={"height": "460px"},
                ),

                # Divider
                html.Div(style={"borderTop": f"1px solid {BORDER_COLOR}", "margin": "14px 0 12px"}),

                # Header for Volume Chart + User Hint
                html.Div(
                    style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "4px"},
                    children=[
                        html.Div(id="volume-mode-badge", style={"fontSize": "0.80rem", "fontWeight": 700, "color": TEXT_NAVY}),
                        html.Div(
                            "💡 Click a bar to zoom into price activity",
                            style={"fontSize": "0.75rem", "fontWeight": 600, "color": TEXT_SECONDARY, "backgroundColor": "#f1f5f9", "padding": "3px 8px", "borderRadius": "4px", "border": f"1px solid {BORDER_COLOR}"}
                        ),
                    ],
                ),
                # Trading Volume Chart (Directly below Candlestick)
                dcc.Graph(
                    id="volume-chart",
                    config={"displayModeBar": False},
                    style={"height": "210px"},
                ),
            ],
        ),

        # ── 4. Separate Card: Returns Histogram ───────────────────
        html.Div(
            style={**CARD_STYLE, "marginBottom": "24px"},
            children=[
                html.Div(
                    style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "6px"},
                    children=[
                        html.Div(
                            "Daily Returns Volatility Distribution",
                            style={"fontSize": "0.85rem", "fontWeight": 700, "color": TEXT_NAVY}
                        ),
                        html.Div(
                            className="chart-color-key",
                            children=[
                                color_key_item("Negative returns (<0%)", COLOR_SLATE),
                                html.Span(id="positive-returns-label"),
                            ]
                        ),
                    ],
                ),
                html.Div(id="returns-reference-key", className="returns-reference-key"),
                dcc.Graph(
                    id="returns-histogram",
                    config={"displayModeBar": False},
                    style={"height": "260px"},
                ),
            ],
        ),

        # ── State Stores ──────────────────────────────────────────
        dcc.Store(id="clicked-date-store", data=None),
        dcc.Store(id="active-preset-store", data="latest" if has_comparison else "1y"),
    ],
)

# ══════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════

# ── 1. Preset Buttons, Dragged Slider & Volume Click Interaction ──
@app.callback(
    Output("date-slider", "value"),
    Output("clicked-date-store", "data"),
    Output("active-preset-store", "data"),
    Input("btn-1y", "n_clicks"),
    Input("btn-5y", "n_clicks"),
    Input("btn-10y", "n_clicks"),
    Input("btn-max", "n_clicks"),
    Input("btn-reset-zoom", "n_clicks"),
    Input("btn-latest", "n_clicks"),
    Input("btn-announcement", "n_clicks"),
    Input("detail-stock", "value"),
    Input("volume-chart", "clickData"),
    Input("date-slider", "value"),
    State("active-preset-store", "data"),
    prevent_initial_call=True,
)
def handle_interactions(
    btn_1y, btn_5y, btn_10y, btn_max, btn_reset, btn_latest, btn_event,
    ticker, click_data, slider_val, active_preset,
):
    trigger = callback_context.triggered_id
    if trigger in ("btn-1y", "btn-5y", "btn-10y", "btn-max"):
        preset = trigger.removeprefix("btn-")
        return PRESET_WINDOWS[preset], None, preset

    if trigger in ("btn-latest", "btn-announcement"):
        preset = trigger.removeprefix("btn-")
        if preset in PRESET_WINDOWS:
            return PRESET_WINDOWS[preset], None, preset

    if trigger in ("btn-reset-zoom", "detail-stock"):
        return no_update, None, no_update

    if trigger == "volume-chart" and click_data and click_data.get("points"):
        point_x = click_data["points"][0].get("x")
        if point_x:
            return no_update, {"date": point_x[:10], "ticker": ticker}, no_update

    if trigger == "date-slider":
        if PRESET_WINDOWS.get(active_preset) == slider_val:
            return no_update, None, no_update
        presets = ("max",) if has_comparison else PRESET_WINDOWS
        preset = next((key for key in presets if PRESET_WINDOWS[key] == slider_val), None)
        return no_update, None, preset

    return no_update, no_update, no_update


@app.callback(
    Output("comparison-chart", "figure"),
    Input("date-slider", "value"),
    Input("active-preset-store", "data"),
)
def update_comparison(slider_val, active_preset):
    start, end = map(days_to_date, slider_val)
    fig = go.Figure()
    if has_comparison:
        prices = shared_prices.loc[start:end]
        if not prices.empty:
            rebased = prices.div(prices.iloc[0]).mul(100)
            for ticker, color in TICKER_COLORS.items():
                fig.add_scatter(
                    x=rebased.index, y=rebased[ticker], mode="lines+markers" if len(prices) == 1 else "lines",
                    name=TICKER_NAMES[ticker], line=dict(color=color, width=3),
                    hovertemplate="%{y:$,.2f}",
                )
        if start <= EVENT_DATE <= end:
            selected = active_preset == "announcement"
            fig.add_vline(x=EVENT_DATE, line_color=COLOR_VIOLET, line_dash="dot", line_width=2 if selected else 1)
            if selected:
                fig.add_annotation(
                    x=EVENT_DATE, y=1, yref="paper", text="Nov 12 · NVIDIA CEO announcement",
                    xanchor="right" if EVENT_DATE > start + (end - start) / 2 else "left",
                    yshift=8, yanchor="bottom", showarrow=False, bgcolor=BG_CARD,
                    font=dict(size=12, color=COLOR_VIOLET, weight=600),
                )
    if not fig.data:
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
            text="No shared trading days in this window." if has_comparison else "Awaiting matching AMD and NVDA price exports.",
        )
    apply_light_theme(fig, "")
    fig.update_layout(
        margin=dict(l=70, r=24, t=68, b=40),
        hovermode="x unified",
        hoverlabel=dict(namelength=-1),
        legend=dict(orientation="h", y=1.09, yanchor="bottom", borderwidth=0),
    )
    fig.update_xaxes(
        type="date", hoverformat="%b %d, %Y",
        range=[start - pd.Timedelta(hours=12), end + pd.Timedelta(hours=12)],
    )
    fig.update_yaxes(visible=bool(fig.data), tickprefix="$", title="Value of $100 at window start")
    return fig


# ── 2. Dynamic Styling of Segmented Preset Buttons ────────────────
@app.callback(
    Output("btn-1y", "className"),
    Output("btn-5y", "className"),
    Output("btn-10y", "className"),
    Output("btn-max", "className"),
    Output("btn-announcement", "aria-pressed"),
    Output("btn-latest", "aria-pressed"),
    Input("active-preset-store", "data"),
)
def update_preset_classes(active_preset):
    base_class = "dashboard-button preset-button"
    return tuple(
        f"{base_class} is-active" if preset == active_preset else base_class
        for preset in ("1y", "5y", "10y", "max")
    ) + tuple(str(active_preset == view).lower() for view in ("announcement", "latest"))


# ── 3. Headline Metric Cards, Sparkline & Slider Label ────────────
@app.callback(
    Output("kpi-tiles", "children"),
    Output("slider-range-label", "children"),
    Input("date-slider", "value"),
    Input("detail-stock", "value"),
)
def update_kpis(slider_val, ticker):
    df_daily = detail_data[ticker]
    start_dt = days_to_date(slider_val[0])
    end_dt = days_to_date(slider_val[1])

    mask = df_daily["Date"].between(start_dt, end_dt)
    df_slice = df_daily.loc[mask]

    range_txt = f"{start_dt.strftime('%b %d, %Y')}  ➔  {end_dt.strftime('%b %d, %Y')}"

    if df_slice.empty:
        return [], range_txt

    first_row = df_slice.iloc[0]
    last_row = df_slice.iloc[-1]

    start_close = first_row["Close"]
    end_close = last_row["Close"]
    net_change = end_close - start_close
    pct_change = (net_change / start_close) * 100 if start_close > 0 else 0.0

    avg_vol = df_slice["Volume"].mean()
    vol_std = df_slice["Daily_Return_Pct"].dropna().std()

    chg_color = TICKER_COLORS[ticker] if net_change >= 0 else COLOR_SLATE
    chg_sign = "+" if net_change >= 0 else ""

    # Generate mini sparkline for the Period Close Price card
    # Downsample if series is long so sparkline stays fast
    spark_df = df_slice
    if len(spark_df) > 300:
        step = len(spark_df) // 300
        spark_df = spark_df.iloc[::step]

    spark_fig = go.Figure(
        go.Scatter(
            x=spark_df["Date"],
            y=spark_df["Close"],
            mode="lines",
            line=dict(color=TICKER_COLORS[ticker], width=1.5),
            fill="tozeroy",
            hoverinfo="none",
        )
    )
    spark_fig.update_layout(
        margin=dict(l=0, r=0, t=2, b=0),
        xaxis=dict(visible=False, showgrid=False),
        yaxis=dict(visible=False, showgrid=False),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=38,
    )

    close_card = html.Div(
        style={**CARD_STYLE, "padding": "14px 18px"},
        children=[
            html.P("Period Close Price", style={"margin": 0, "fontSize": "0.72rem", "color": TEXT_MUTED, "fontWeight": 600, "textTransform": "uppercase", "letterSpacing": "0.03em"}),
            html.H3(f"${end_close:,.2f}", style={"margin": "4px 0 2px", "fontSize": "1.55rem", "fontWeight": 700, "color": TEXT_NAVY, "letterSpacing": "-0.01em"}),
            html.P(f"Start: ${start_close:,.2f} · Net: {chg_sign}${net_change:,.2f}", style={"margin": "0 0 6px 0", "fontSize": "0.68rem", "color": TEXT_MUTED}),
            dcc.Graph(figure=spark_fig, config={"displayModeBar": False}),
        ],
    )

    return_card = html.Div(
        style={**CARD_STYLE, "padding": "14px 18px"},
        children=[
            html.P("Period Return (%)", style={"margin": 0, "fontSize": "0.72rem", "color": TEXT_MUTED, "fontWeight": 600, "textTransform": "uppercase", "letterSpacing": "0.03em"}),
            html.H3(f"{chg_sign}{pct_change:,.2f}%", style={"margin": "6px 0 3px", "fontSize": "1.55rem", "fontWeight": 700, "color": chg_color, "letterSpacing": "-0.01em"}),
            html.P(f"Directional price change over {len(df_slice):,} trading sessions", style={"margin": 0, "fontSize": "0.70rem", "color": TEXT_MUTED}),
        ],
    )

    volume_card = html.Div(
        style={**CARD_STYLE, "padding": "14px 18px"},
        children=[
            html.P("Avg Daily Volume", style={"margin": 0, "fontSize": "0.72rem", "color": TEXT_MUTED, "fontWeight": 600, "textTransform": "uppercase", "letterSpacing": "0.03em"}),
            html.H3(f"{avg_vol / 1e6:,.2f} M", style={"margin": "6px 0 3px", "fontSize": "1.55rem", "fontWeight": 700, "color": TEXT_SECONDARY, "letterSpacing": "-0.01em"}),
            html.P(f"Total volume: {df_slice['Volume'].sum() / 1e9:,.2f} B shares", style={"margin": 0, "fontSize": "0.70rem", "color": TEXT_MUTED}),
        ],
    )

    volatility_card = html.Div(
        style={**CARD_STYLE, "padding": "14px 18px"},
        children=[
            html.P("Return Volatility (Std Dev)", style={"margin": 0, "fontSize": "0.72rem", "color": TEXT_MUTED, "fontWeight": 600, "textTransform": "uppercase", "letterSpacing": "0.03em"}),
            html.H3(f"{vol_std:,.2f}%" if pd.notna(vol_std) else "N/A", style={"margin": "6px 0 3px", "fontSize": "1.55rem", "fontWeight": 700, "color": TEXT_MUTED, "letterSpacing": "-0.01em"}),
            html.P("Annualized volatility: " + (f"{vol_std * 252**0.5:,.1f}%" if pd.notna(vol_std) else "N/A"), style={"margin": 0, "fontSize": "0.70rem", "color": TEXT_MUTED}),
        ],
    )

    return [close_card, return_card, volume_card, volatility_card], range_txt


# ── 4. Candlestick Chart ──────────────────────────────────────────
@app.callback(
    Output("candlestick-chart", "figure"),
    Output("candlestick-mode-badge", "children"),
    Output("zoom-status-badge", "children"),
    Output("candlestick-key", "children"),
    Input("date-slider", "value"),
    Input("clicked-date-store", "data"),
    Input("detail-stock", "value"),
)
def update_candlestick(slider_val, zoom, ticker):
    df_daily = detail_data[ticker]
    key = [
        color_key_item(f"{TICKER_NAMES[ticker]} up or flat (Close ≥ Open)", TICKER_COLORS[ticker]),
        color_key_item(DOWN, COLOR_SLATE),
    ]
    df_weekly = weekly_data[ticker]
    clicked_date = zoom["date"] if zoom and zoom["ticker"] == ticker else None
    start_dt = days_to_date(slider_val[0])
    end_dt = days_to_date(slider_val[1])
    span_years = (end_dt - start_dt).days / 365.25

    # Check if a volume bar was clicked for daily zoom
    if clicked_date:
        center_dt = pd.to_datetime(clicked_date)
        pos = (df_daily["Date"] - center_dt).abs().idxmin()
        low_idx = max(0, pos - 10)
        high_idx = min(len(df_daily) - 1, pos + 10)
        zoom_df = df_daily.iloc[low_idx : high_idx + 1]

        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=zoom_df["Date"],
                    open=zoom_df["Open"],
                    high=zoom_df["High"],
                    low=zoom_df["Low"],
                    close=zoom_df["Close"],
                    increasing_line_color=TICKER_COLORS[ticker],
                    decreasing_line_color=COLOR_SLATE,
                    increasing_fillcolor=TICKER_COLORS[ticker],
                    decreasing_fillcolor=COLOR_SLATE,
                    name="Daily OHLC",
                    text=[
                        f"Date: {d.strftime('%b %d, %Y')}<br>Open: ${o:,.2f}<br>High: ${h:,.2f}<br>Low: ${l:,.2f}<br>Close: ${c:,.2f}<br>Range: ${h-l:,.2f}"
                        for d, o, h, l, c in zip(zoom_df["Date"], zoom_df["Open"], zoom_df["High"], zoom_df["Low"], zoom_df["Close"])
                    ],
                    hoverinfo="text",
                )
            ]
        )
        fig.update_layout(xaxis_rangeslider_visible=False)
        apply_light_theme(
            fig,
            f"{ticker} Zoomed Daily Candlestick View (±10 Trading Days around {center_dt.strftime('%b %d, %Y')})"
        )
        align_market_chart(fig, zoom_df["Date"].min(), zoom_df["Date"].max(), show_dates=True)
        fig.update_yaxes(tickprefix="$", tickformat=",.2~f")
        mode_badge = "Daily OHLC (Zoomed Inspection View)"
        zoom_badge = f"📍 Selected Date/Week: {center_dt.strftime('%b %d, %Y')} · (Session {pos + 1:,} of {len(df_daily):,})"
        return fig, mode_badge, zoom_badge, key

    # Standard view
    if span_years > 3.0:
        mask = df_weekly["Date"].between(start_dt, end_dt)
        plot_df = df_weekly.loc[mask]
        data_res = "Weekly Aggregated"
        mode_badge = "Weekly OHLC Candles (Click any volume bar below to inspect Daily candles)"
    else:
        mask = df_daily["Date"].between(start_dt, end_dt)
        plot_df = df_daily.loc[mask]
        data_res = "Daily"
        mode_badge = "Daily OHLC Candles"

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=plot_df["Date"],
                open=plot_df["Open"],
                high=plot_df["High"],
                low=plot_df["Low"],
                close=plot_df["Close"],
                increasing_line_color=TICKER_COLORS[ticker],
                decreasing_line_color=COLOR_SLATE,
                increasing_fillcolor=TICKER_COLORS[ticker],
                decreasing_fillcolor=COLOR_SLATE,
                name=f"{data_res} OHLC",
                text=[
                    f"Date: {d.strftime('%b %d, %Y')}<br>Open: ${o:,.2f}<br>High: ${h:,.2f}<br>Low: ${l:,.2f}<br>Close: ${c:,.2f}<br>Range: ${h-l:,.2f}"
                    for d, o, h, l, c in zip(plot_df["Date"], plot_df["Open"], plot_df["High"], plot_df["Low"], plot_df["Close"])
                ],
                hoverinfo="text",
            )
        ]
    )

    # Initial March 17, 1980 session milestone
    if not has_comparison and plot_df["Date"].min() <= MIN_DATE + pd.Timedelta(days=7):
        fig.add_annotation(
            x=MIN_DATE,
            y=df_daily.loc[0, "Close"],
            text=f"First Close: ${df_daily.loc[0, 'Close']:.2f}<br>({MIN_DATE:%B %d, %Y})",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=1.5,
            arrowcolor=TEXT_NAVY,
            ax=36,
            ay=-36,
            bgcolor="#ffffff",
            bordercolor=BORDER_COLOR,
            borderwidth=1,
            font=dict(color=TEXT_NAVY, size=10, weight=600),
        )

    fig.update_layout(xaxis_rangeslider_visible=False)
    apply_light_theme(fig, f"{ticker} Price Action ({data_res} Candlestick Chart · {start_dt.strftime('%b %Y')} to {end_dt.strftime('%b %Y')})")
    align_market_chart(fig, start_dt, end_dt, show_dates=False)
    fig.update_yaxes(tickprefix="$", tickformat=",.2~f")
    zoom_badge = "Showing full selected date window"
    return fig, mode_badge, zoom_badge, key


# ── 5. Trading Volume Bar Chart ───────────────────────────────────
@app.callback(
    Output("volume-chart", "figure"),
    Output("volume-mode-badge", "children"),
    Input("date-slider", "value"),
    Input("clicked-date-store", "data"),
    Input("detail-stock", "value"),
)
def update_volume(slider_val, zoom, ticker):
    df_daily = detail_data[ticker]
    df_weekly = weekly_data[ticker]
    clicked_date = zoom["date"] if zoom and zoom["ticker"] == ticker else None
    start_dt = days_to_date(slider_val[0])
    end_dt = days_to_date(slider_val[1])
    span_years = (end_dt - start_dt).days / 365.25

    if span_years > 3.0:
        mask = df_weekly["Date"].between(start_dt, end_dt)
        plot_df = df_weekly.loc[mask].copy()
        data_label = "Weekly"
        mode_text = "Trading Volume: Weekly Aggregation"
    else:
        mask = df_daily["Date"].between(start_dt, end_dt)
        plot_df = df_daily.loc[mask].copy()
        data_label = "Daily"
        mode_text = "Trading Volume: Daily Sessions"

    color_map = {
        UP_OR_FLAT: TICKER_COLORS[ticker],
        DOWN: COLOR_SLATE,
    }

    # Format hover text cleanly
    plot_df["hover_txt"] = [
        f"Date: {d.strftime('%b %d, %Y')}<br>Volume: {v:,} shares<br>Open: ${o:,.2f}<br>Close: ${c:,.2f}"
        for d, v, o, c in zip(plot_df["Date"], plot_df["Volume"], plot_df["Open"], plot_df["Close"])
    ]

    fig = px.bar(
        plot_df,
        x="Date",
        y="Volume",
        color="Direction",
        color_discrete_map=color_map,
        category_orders={"Direction": [UP_OR_FLAT, DOWN]},
        custom_data=["hover_txt"],
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>",
    )

    if clicked_date:
        clicked_dt = pd.Timestamp(clicked_date)
        matching = plot_df.loc[plot_df["Date"] == clicked_dt, "Volume"]
        if not matching.empty:
            for trace in fig.data:
                trace.marker.line = dict(
                    color=TEXT_NAVY,
                    width=[2.5 if pd.Timestamp(date) == clicked_dt else 0 for date in trace.x],
                )
            fig.add_annotation(
                x=clicked_dt,
                y=matching.iloc[0],
                text="Selected",
                showarrow=True,
                arrowhead=2,
                arrowwidth=1.5,
                arrowcolor=TEXT_NAVY,
                ax=0,
                ay=-24,
                bgcolor=BG_CARD,
                bordercolor=TEXT_NAVY,
                borderwidth=1,
                font=dict(color=TEXT_NAVY, size=9, weight=600),
            )

    fig.update_layout(
        bargap=0.1,
        clickmode="event",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            title_text="",
        ),
    )
    apply_light_theme(fig, f"{ticker} Trading Volume ({data_label})")
    align_market_chart(fig, start_dt, end_dt, show_dates=True)
    fig.update_yaxes(exponentformat="B", showexponent="all")
    return fig, mode_text


def reference_key_item(label, color, line_style):
    return html.Span(
        [
            html.Span(
                className="returns-reference-swatch",
                style={"borderTopColor": color, "borderTopStyle": line_style},
                **{"aria-hidden": "true"},
            ),
            label,
        ],
        className="returns-reference-item",
    )


# ── 6. Split Returns Volatility Histogram
@app.callback(
    Output("returns-histogram", "figure"),
    Output("returns-reference-key", "children"),
    Output("positive-returns-label", "children"),
    Input("date-slider", "value"),
    Input("detail-stock", "value"),
)
def update_histogram(slider_val, ticker):
    df_daily = detail_data[ticker]
    start_dt = days_to_date(slider_val[0])
    end_dt = days_to_date(slider_val[1])

    mask = df_daily["Date"].between(start_dt, end_dt)
    df_slice = df_daily.loc[mask]
    returns = df_slice["Daily_Return_Pct"].dropna()

    fig = go.Figure()
    reference_key = []

    if not returns.empty:
        mean_ret = returns.mean()
        std_ret = returns.std()

        neg_returns = returns[returns < 0]
        pos_returns = returns[returns >= 0]

        # Calculate reasonable bin size based on range
        min_val = returns.min()
        max_val = returns.max()
        bin_size = max(0.25, round((max_val - min_val) / 60, 2))

        if not neg_returns.empty:
            fig.add_trace(
                go.Histogram(
                    x=neg_returns,
                    xbins=dict(start=min_val - bin_size, end=0, size=bin_size),
                    marker_color=COLOR_SLATE,
                    opacity=0.88,
                    name="Negative returns (<0%)",
                    hovertemplate="Negative Return: %{x}%<br>Count: %{y:,} sessions<extra></extra>",
                )
            )

        if not pos_returns.empty:
            fig.add_trace(
                go.Histogram(
                    x=pos_returns,
                    xbins=dict(start=0, end=max_val + bin_size, size=bin_size),
                    marker_color=TICKER_COLORS[ticker],
                    opacity=0.88,
                    name="Nonnegative returns (≥0%)",
                    hovertemplate="Nonnegative return: %{x}%<br>Count: %{y:,} sessions<extra></extra>",
                )
            )

        # Distinct solid Zero Line to immediately split gains & losses
        fig.add_vline(
            x=0,
            line_width=2.2,
            line_color=COLOR_ZERO,
            line_dash="solid",
            annotation_text="0% (Break-even)",
            annotation_position="top",
            annotation_font=dict(color=COLOR_ZERO, size=10, weight=700),
        )

        fig.add_vline(x=mean_ret, line_width=1.6, line_dash="dash", line_color=COLOR_MEAN)
        reference_key.append(reference_key_item(f"Mean {mean_ret:.2f}%", COLOR_MEAN, "dashed"))

        if pd.notna(std_ret) and std_ret > 0:
            lower = mean_ret - 2 * std_ret
            upper = mean_ret + 2 * std_ret
            fig.add_vline(x=lower, line_width=1.4, line_dash="dot", line_color=COLOR_SLATE)
            fig.add_vline(x=upper, line_width=1.4, line_dash="dot", line_color=TICKER_COLORS[ticker])
            reference_key.extend([
                reference_key_item(f"−2σ {lower:.1f}%", COLOR_SLATE, "dotted"),
                reference_key_item(f"+2σ {upper:.1f}%", TICKER_COLORS[ticker], "dotted"),
            ])

    fig.update_layout(
        barmode="overlay",
        xaxis_title="Daily Return (%)",
        yaxis_title="Trading Days Count",
        showlegend=False,
    )
    volatility = returns.std()
    summary = f"{len(returns):,} trading days"
    if pd.notna(volatility):
        summary += f" · Volatility σ {volatility:.2f}%"
    apply_light_theme(fig, "")
    fig.update_layout(margin=dict(l=56, r=24, t=22, b=46))
    reference_key.insert(0, html.Span(summary))
    return fig, reference_key, color_key_item(
        f"{TICKER_NAMES[ticker]} nonnegative returns (≥0%)", TICKER_COLORS[ticker],
    )


# ══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8052))
    app.run(host="0.0.0.0", port=port, debug=False)
