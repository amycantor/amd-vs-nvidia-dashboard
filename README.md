# AMD vs. NVIDIA Stock Explorer

Python Dash dashboard comparing AMD and NVIDIA in 2026, with the original AMD historical explorer available when the comparison files are missing.

## Quick Start (local)

```bash
cd /Users/amycantor/.gemini/antigravity/scratch/amd-stock-dashboard
pip install -r requirements.txt
python app.py
# → Opens on http://127.0.0.1:8052
```

## Load the 2026 comparison

1. Open [AMD Historical Data](https://finance.yahoo.com/quote/AMD/history/) and [NVIDIA Historical Data](https://finance.yahoo.com/quote/NVDA/history/) in Yahoo Finance.
2. On each page, set a custom date range from January 1, 2026 through the latest completed session. Select **Historical Prices** and **Daily**, apply the filters, then select **Download**. Yahoo Finance may require a sign-in or a plan with historical downloads.
3. Save the files next to `app.py` as `AMD_2026.csv` and `NVDA_2026.csv`. Keep the `Date, Open, High, Low, Close, Volume` columns. The dashboard uses Yahoo's split-adjusted `Close` field. Restart the app after adding or refreshing the files.

The comparison uses only dates present in both exports and rebases both stocks to $100 at the first shared session in the selected window. **Latest** ends on the last shared session and shows up to 30 calendar days. Select a stock under **Stock detail** to change the metrics, candlestick, volume bars, and daily returns histogram.

The [November 12 NVIDIA announcement](https://nvidianews.nvidia.com/news/nvidia-announces-ceo-transition) opens a window starting one week before the announcement and ending at the 20th post-announcement session or the last available shared session, whichever comes first. Reaction figures compare the November 11 close to the closes on November 13, November 19, and December 11, per the [Nasdaq trading calendar](https://www.nasdaq.com/trading-calendar). A missing baseline or endpoint displays as **Window incomplete**. The figures describe stock moves around the announcement.

## Render Deployment

1. Put `app.py`, `requirements.txt`, `AMD_stock_data_1980_2026.csv`, `AMD_2026.csv`, `NVDA_2026.csv`, `assets/`, and `README.md` at the root of a dedicated GitHub repository.
2. Link the repository to Render as a new **Web Service**.
3. Configuration:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:server`
   - **Environment Variable**: `PYTHON_VERSION=3.11` (or 3.10+)

## Data Handling & Notes
- **Missing Initial Return**: The dataset begins on March 17, 1980 (`1980-03-17`). Because there is no predecessor trading day in the dataset, row 0 has a `NaN` value for `Daily_Return_Pct`. When constructing the **Daily Returns Volatility Distribution** histogram and calculating return standard deviation ($\sigma$), this missing first return is filtered out using `.dropna()`. The row is fully preserved in price and volume calculations so AMD's starting IPO price ($3.15) and initial volume (219,600) remain historically accurate.
- **Dynamic Resolution**: To ensure instant rendering and low memory usage across 46 years, the Candlestick and Volume charts switch dynamically between **Daily** resolution ($\le 3$ years) and **Weekly Aggregated** OHLC ($> 3$ years).

## Features & Visuals
1. **Interactive Candlestick Chart (Advanced)**:
   - Features crosshair spike lines and detailed hover details (Date, Open, High, Low, Close, and Range).
   - The historical AMD view labels the first recorded closing price in the dataset ($3.15 on March 17, 1980).
   - "↺ Reset Zoom" button is located directly next to the candlestick title.
2. **Trading Volume Bar Chart with Click-to-Zoom**:
   - Volume bars sit directly below the candlestick chart so X-axis dates visually align.
   - Candles and volume bars use the selected stock’s color (teal for AMD, violet for NVIDIA) for up or flat sessions and slate gray for down sessions.
   - Clicking any bar highlights it, displays the selected session badge above the zoomed candlestick view, and opens a $\pm 10$ trading-day daily OHLC view.
3. **Daily Returns Volatility Distribution**:
   - The histogram uses slate gray for negative daily returns ($< 0\%$) and the selected stock’s color for nonnegative daily returns ($\ge 0\%$).
   - A distinct dark zero line clearly marks the boundary between gains and losses.
   - Shows a key above the chart with mean daily return and $\pm 2\sigma$ volatility boundaries.
4. **Headline Metric Cards**:
   - Includes a mini closing-price trend sparkline directly inside the **Period Close Price** card.
   - Explicit signed percentage with direction indicator for **Period Return (%)**.
   - Segmented control presets (`1Y`, `5Y`, `10Y`, `Max`) with clean active pill state that automatically clears when dragging the custom slider handles.
