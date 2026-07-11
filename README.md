# Stock Backtester (US + European Markets)

A local Python backtesting toolkit that:
- Downloads daily price history for US and European stocks via **yfinance** (Yahoo Finance)
- Stores everything in a local **SQLite** database (via SQLAlchemy)
- Runs vectorized backtests for several built-in strategies, with realistic commission + slippage costs and no look-ahead bias
- Persists every run's results and trade log to the database
- Generates ranked result tables and an HTML report with equity-curve charts

## Quick launch (skip the setup below if you just want it running now)

**On your own computer, one click:**
- Windows: double-click `run_app.bat`
- macOS: double-click `run_app.command` (first time only, you may need to
  right-click → Open once to bypass Gatekeeper's "unidentified developer" warning)
- Linux: double-click `run_app.sh`, or run `./run_app.sh` in a terminal

First run creates a private Python environment and installs everything
(~1-2 minutes); every run after that opens in a few seconds. It starts the
app and opens it in your browser automatically at `http://localhost:8501`.
To stop it, close the terminal window it opened.

**As a permanent link you can open from any device:** see `DEPLOY.md` for
a free hosting walkthrough (Streamlit Community Cloud) -- you get a URL
like `https://your-app.streamlit.app` to bookmark.

## 1. Setup (manual / CLI usage)

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Requires internet access to Yahoo Finance to fetch data (this runs on your own machine, not in a sandboxed environment).

## 2. Fetch data

European tickers use a Yahoo Finance suffix (`.DE` Xetra, `.PA` Paris, `.AS` Amsterdam,
`.MI` Milan, `.MC` Madrid, `.SW` Swiss, `.L` London, `.ST`/`.CO`/`.HE`/`.OL` Nordics — see `tickers.py`).

```bash
# Specific tickers (mix US and EU freely)
python cli.py fetch --symbols AAPL,MSFT,SAP.DE,ASML.AS,SHEL.L --start 2015-01-01

# A curated ~55-stock European blue-chip universe
python cli.py fetch --universe EU --start 2015-01-01

# Current S&P 500 constituents (scraped live from Wikipedia, falls back to a
# ~30-stock hardcoded list if that fails)
python cli.py fetch --universe US --start 2015-01-01

# Both US + EU universes at once
python cli.py fetch --universe ALL --start 2015-01-01

# Quick test with just the first 10 tickers
python cli.py fetch --universe US --limit 10 --start 2020-01-01
```

### Fetching one specific exchange (e.g. all of Nasdaq Helsinki / OMXH)

Every curated ticker list is organized per-exchange, so you can pull just one:

```bash
python cli.py list-exchanges
# Exchange code         # curated tickers
# NASDAQ_HELSINKI                     192
# XETRA                                14
# LSE                                  10
# ...

python cli.py fetch --exchange NASDAQ_HELSINKI --start 2015-01-01
```

`NASDAQ_HELSINKI` is a full snapshot of **all ~192 tickers** listed on Nasdaq
Helsinki (sourced from stockanalysis.com, July 2026) -- not just blue chips.
Two caveats worth knowing:
- It's a point-in-time snapshot and will drift (delistings, renames, new
  IPOs). For a guaranteed-current list, re-export one yourself and use
  `--csv` (see below).
- A handful of entries are dual-listed Nordic companies (e.g. Ericsson,
  Nordea, SSAB, Telia) whose primary Yahoo Finance listing is on another
  exchange (e.g. Stockholm) -- their `.HE` ticker may return no data even
  though the company is real. `fetch` reports per-symbol errors without
  failing the whole batch, so this is safe to just try; expect a small
  number of "no data" results mixed in with the successes.

Other available exchange codes: `XETRA` (Germany), `EURONEXT_PARIS`, `EURONEXT_AMSTERDAM`,
`BORSA_ITALIANA`, `BOLSA_MADRID`, `SIX` (Switzerland), `LSE` (UK),
`NASDAQ_STOCKHOLM`, `NASDAQ_COPENHAGEN`, `OSLO_BORS` -- these remain curated
blue-chip subsets rather than full exchange listings; use `--csv` for a
complete list on any of them.

### Fetching every NASDAQ-listed US stock (not just the S&P 500)

`--universe US` gives you the S&P 500 (~500 large caps). For the **complete**
list of everything natively listed on Nasdaq -- typically 3,000-4,500
tickers, live-fetched from Nasdaq's own official Symbol Directory feed
(updated by Nasdaq multiple times a day) -- use:

```bash
python cli.py fetch --universe NASDAQ_FULL --limit 50 --start 2020-01-01
```

**Strongly recommend starting with `--limit`** (e.g. 50-100) to test before
removing it. Fetching the full universe means thousands of individual
Yahoo Finance requests -- it can take a long time and may get you
rate-limited. ETFs and test issues are excluded by default.

### Importing a fully custom/complete ticker list from CSV

For any exchange where you need a guaranteed-complete, authoritative list
(rather than a curated or snapshotted one):

1. Download it yourself from the exchange (e.g. Nasdaq Nordic's instrument list at
   https://www.nasdaqomxnordic.com) or your broker, as a CSV with at least a `symbol` column.
2. Import it directly:

```bash
python cli.py fetch --csv my_omxh_tickers.csv --csv-market EU --start 2015-01-01
```

CSV format (only `symbol` is required; other columns are optional):
```csv
symbol,name,exchange,currency,sector
NOKIA.HE,Nokia Oyj,NASDAQ HELSINKI,EUR,Technology
QTCOM.HE,Qt Group Oyj,NASDAQ HELSINKI,EUR,Technology
```
Symbols must already be in the exact format yfinance expects (ticker + exchange
suffix, e.g. `NOKIA.HE`) — search unfamiliar ones on https://finance.yahoo.com
to confirm before importing.

```bash
python cli.py list-stocks              # everything in the DB
python cli.py list-stocks --market EU  # just EU stocks
```

## 3. Run a backtest

```bash
python cli.py list-strategies
```

Built-in strategies (14 total):

**Trend-following / "seeking trends":**
- `sma_cross` -- classic golden/death cross (fast SMA vs. slow SMA)
- `macd` -- MACD line crossing its signal line
- `supertrend` -- ATR-based trailing band that flips with the trend; rides
  a trend for its full duration rather than exiting on every wiggle
- `adx_trend` -- +DI/-DI direction filtered by ADX trend-strength, so it
  only trades when the market is actually trending (not choppy/sideways)
- `parabolic_sar` -- trailing-stop-style flip system; tightens as a trend extends
- `donchian_breakout` -- turtle-style N-day high/low channel breakout
- `ichimoku_cloud` -- long only when price is above the cloud AND the
  short-term line confirms (near-term + medium-term trend agreement)
- `ma_ribbon` -- long only when three SMAs (short/mid/long) are stacked in
  bullish order, a simple trend-strength confirmation filter

**Mean-reversion / momentum oscillators (buy oversold, sell overbought):**
- `rsi_mean_reversion` -- classic RSI oversold/overbought
- `bollinger_bands` -- long below the lower band, exit above the middle band
- `stochastic_oscillator` -- %K/%D oversold/overbought
- `cci_trend` -- Commodity Channel Index breakout/momentum filter
- `williams_r` -- %R oversold/overbought (inverted stochastic)

**Baseline:**
- `buy_and_hold` -- always long, used as the benchmark comparison

```bash
# One strategy across specific symbols
python cli.py backtest --strategy sma_cross --params fast=20,slow=100 \
    --symbols AAPL,MSFT,SAP.DE --start 2018-01-01

# Across every EU stock currently in the database
python cli.py backtest --strategy rsi_mean_reversion \
    --params period=14,oversold=30,overbought=60 --market EU --start 2018-01-01

# Across every US stock currently in the database
python cli.py backtest --strategy macd --market US --start 2018-01-01

# Across literally everything in the DB (omit --symbols and --market)
python cli.py backtest --strategy donchian_breakout --params entry_window=55,exit_window=20
```

Useful flags: `--capital 10000`, `--commission 0.001` (0.1%/side), `--slippage 0.0005`, `--start`, `--end`.

## 4. Web UI (Streamlit) — a friendlier alternative to the CLI

If you'd rather use dropdowns, date pickers, and number inputs than CLI flags,
`streamlit_app.py` gives you the same functionality (fetch data, configure a
strategy, run a backtest, and see the price chart with buy/sell markers) in
a browser tab.

**Run it locally:**
```bash
streamlit run streamlit_app.py
```
This opens `http://localhost:8501` automatically.

**Run it in Google Colab** (Colab has no way to expose a local port to your
browser directly, so tunnel it with `pyngrok`):
```python
!pip install -q streamlit pyngrok

!streamlit run streamlit_app.py --server.headless true &>/content/logs.txt &

from pyngrok import ngrok
# first time only: ngrok.set_auth_token("your_free_token_from_ngrok.com")
public_url = ngrok.connect(8501)
print(public_url)
```
Click the printed URL to open the app. (`ngrok`'s free tier requires a free
account + auth token — sign up at ngrok.com, it takes a minute.)

In the UI: use the sidebar to fetch data (preset universe, a specific
exchange like `NASDAQ_HELSINKI`, specific tickers, or upload your own CSV),
then use the main panel to pick a strategy, set the date range and initial
capital, and click **Run Backtest**. Results show as a ranked table plus a
price chart with buy/sell markers for any symbol you select.

## 5. Inspect results (CLI)

```bash
python cli.py runs                     # list all past backtest runs
python cli.py results --run-id 3       # full ranked metrics table for a run
python cli.py report --run-id 3 --top 10   # HTML report + equity-curve PNGs
```

The report is written to `reports/run_<id>/report.html` — open it in a browser.

## 6. Metrics reported

Total return, CAGR, annualized volatility, Sharpe ratio, Sortino ratio, max
drawdown, Calmar ratio, win rate, profit factor, number of trades, final
equity, and the buy-&-hold return for the same period as a benchmark.

## 7. Project layout

```
config.py        - paths, DB URL, default trading assumptions
database.py      - SQLAlchemy models (Stock, PriceBar, BacktestRun, BacktestResult, Trade)
tickers.py       - US (S&P 500, scraped live) and EU (curated blue-chip) ticker universes
data_fetcher.py  - yfinance -> database ingestion
strategies.py    - Strategy base class + built-in strategies (add your own here)
backtester.py    - vectorized backtest engine + DB persistence
metrics.py       - Sharpe/Sortino/CAGR/drawdown/etc. calculations
reporting.py     - HTML report + matplotlib equity-curve charts
cli.py           - command-line entry point (see examples above)
streamlit_app.py - browser-based UI (see section 4 above)
```

## 8. Adding your own strategy

Add a class to `strategies.py`:

```python
class MyStrategy(Strategy):
    name = "my_strategy"
    param_info = {"lookback": "days to look back (default 30)"}

    def generate_signals(self, df):
        # df has a 'close' column indexed by date.
        # Return a pandas Series of 1 (long) / 0 (flat) per date.
        lookback = int(self.params.get("lookback", 30))
        momentum = df["close"] / df["close"].shift(lookback) - 1
        signal = (momentum > 0).astype(int)
        return signal
```

Then register it by adding `MyStrategy` to the `STRATEGY_REGISTRY` list at the
bottom of `strategies.py`. It's immediately available via
`--strategy my_strategy` on the CLI.

## Notes & caveats

- Position sizing is "all-in / all-out" long-only by default (no shorting, no
  partial sizing, no portfolio-level position limits). It's meant as a
  research/screening tool, not a production trading system.
- Prices use Yahoo Finance's adjusted close, so dividends/splits are handled correctly.
- Commission + slippage are charged as a % of trade value on every entry and exit.
- This is not financial advice — backtested performance does not guarantee future results.
