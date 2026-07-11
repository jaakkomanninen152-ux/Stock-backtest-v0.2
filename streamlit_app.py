"""
User-friendly web UI for the stock backtester, built with Streamlit.

Run locally:
    streamlit run streamlit_app.py

Run in Google Colab:
    !pip install -q streamlit pyngrok
    !streamlit run streamlit_app.py &>/content/logs.txt &
    from pyngrok import ngrok
    print(ngrok.connect(8501))
    # (see README.md for the full Colab walkthrough, including auth token setup)
"""
import datetime as dt
import json

import streamlit as st
import pandas as pd
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure

from database import init_db, get_session, Stock, BacktestRun, BacktestResult
from data_fetcher import fetch_and_store, fetch_universe, fetch_exchange, fetch_from_csv
from tickers import get_universe, list_exchanges
from strategies import STRATEGY_REGISTRY, get_strategy
from backtester import load_price_df, run_single_backtest, run_backtest

st.set_page_config(page_title="Stock Backtester", layout="wide")
init_db()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db_symbols(market=None):
    session = get_session()
    q = session.query(Stock)
    if market and market != "ALL":
        q = q.filter_by(market=market)
    symbols = [s.symbol for s in q.order_by(Stock.symbol).all()]
    session.close()
    return symbols


def plot_price_and_equity(stock_symbol, stock_name, df, bt, strategy_name):
    # Uses matplotlib's object-oriented Figure API (not pyplot) so this is
    # safe to call from Streamlit's per-session worker threads -- pyplot's
    # global figure-manager state is not thread-safe and can crash the
    # server if two script reruns touch it concurrently.
    fig = Figure(figsize=(10, 6.5))
    (ax_price, ax_equity) = fig.subplots(
        2, 1, sharex=True, gridspec_kw={"height_ratios": [1.3, 1]},
    )
    ax_price.plot(df.index, df["close"], color="#555", linewidth=1, label="Price")
    trades = bt["trades"]
    if trades:
        buy_dates = [t["entry_date"] for t in trades]
        buy_prices = [df.loc[t["entry_date"], "close"] for t in trades]
        sell_dates = [t["exit_date"] for t in trades]
        sell_prices = [df.loc[t["exit_date"], "close"] for t in trades]
        ax_price.scatter(buy_dates, buy_prices, marker="^", color="#2ecc71", s=90,
                          zorder=5, edgecolors="black", linewidths=0.5, label="Buy")
        ax_price.scatter(sell_dates, sell_prices, marker="v", color="#e74c3c", s=90,
                          zorder=5, edgecolors="black", linewidths=0.5, label="Sell")
    ax_price.set_title(f"{stock_symbol} — {stock_name}")
    ax_price.set_ylabel("Price")
    ax_price.legend(loc="upper left", fontsize=8)

    ax_equity.plot(bt["equity_curve"].index, bt["equity_curve"].values,
                    label=strategy_name, linewidth=1.8)
    ax_equity.plot(bt["benchmark_curve"].index, bt["benchmark_curve"].values,
                    label="Buy & Hold", linewidth=1.2, linestyle="--", alpha=0.7)
    ax_equity.set_ylabel("Equity")
    ax_equity.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Sidebar: data management
# ---------------------------------------------------------------------------
st.sidebar.title("📊 Stock Backtester")
st.sidebar.header("1. Fetch data")

fetch_mode = st.sidebar.radio(
    "Source", ["Preset universe", "Specific exchange", "Specific tickers", "Upload CSV"],
    key="fetch_mode",
)

if fetch_mode == "Preset universe":
    universe_choice = st.sidebar.selectbox("Universe", ["US", "EU", "ALL", "NASDAQ_FULL"])
    if universe_choice == "NASDAQ_FULL":
        st.sidebar.warning(
            "NASDAQ_FULL is every Nasdaq-listed security (~3,000-4,500 tickers). "
            "Strongly recommend setting a small Limit below to test first -- "
            "fetching everything can take a long time and may get rate-limited."
        )
    limit = st.sidebar.number_input("Limit (0 = no limit)", min_value=0, value=25, step=5)
elif fetch_mode == "Specific exchange":
    exchange_counts = list_exchanges()
    exchange_labels = [f"{code} ({n} tickers)" for code, n in sorted(exchange_counts.items())]
    exchange_pick = st.sidebar.selectbox("Exchange", exchange_labels)
    exchange_choice = exchange_pick.split(" (")[0]
    limit = st.sidebar.number_input("Limit (0 = no limit)", min_value=0, value=0, step=5)
    st.sidebar.caption(
        "Curated liquid names per exchange -- not necessarily every listed "
        "company. For a fully complete list, use 'Upload CSV' instead."
    )
elif fetch_mode == "Specific tickers":
    tickers_text = st.sidebar.text_area(
        "Tickers (comma-separated)",
        placeholder="AAPL, MSFT, SAP.DE, ASML.AS, SHEL.L",
    )
else:  # Upload CSV
    csv_file = st.sidebar.file_uploader(
        "CSV with a 'symbol' column (optionally name/exchange/currency/sector)",
        type=["csv"],
    )
    csv_market = st.sidebar.selectbox("Default market label", ["EU", "US"])
    st.sidebar.caption(
        "Use this for a fully complete/authoritative exchange listing you've "
        "downloaded yourself, e.g. from Nasdaq Nordic or your broker."
    )

fetch_start = st.sidebar.date_input("History start", value=dt.date(2018, 1, 1), key="fetch_start")
fetch_end = st.sidebar.date_input("History end", value=dt.date.today(), key="fetch_end")

if st.sidebar.button("⬇️ Fetch data", width='stretch'):
    with st.spinner("Downloading price history from Yahoo Finance..."):
        if fetch_mode == "Preset universe":
            summary = fetch_universe(
                universe_choice, start=fetch_start.isoformat(), end=fetch_end.isoformat(),
                limit=(limit or None),
            )
        elif fetch_mode == "Specific exchange":
            summary = fetch_exchange(
                exchange_choice, start=fetch_start.isoformat(), end=fetch_end.isoformat(),
                limit=(limit or None),
            )
        elif fetch_mode == "Specific tickers":
            symbols = [s.strip() for s in tickers_text.split(",") if s.strip()]
            universe = get_universe("ALL")
            meta = {s: universe[s] for s in symbols if s in universe}
            summary = fetch_and_store(symbols, start=fetch_start.isoformat(),
                                       end=fetch_end.isoformat(), meta=meta)
        else:  # Upload CSV
            if csv_file is None:
                st.sidebar.warning("Please choose a CSV file first.")
                summary = {}
            else:
                tmp_path = "/tmp/uploaded_tickers.csv"
                with open(tmp_path, "wb") as f:
                    f.write(csv_file.getvalue())
                summary = fetch_from_csv(tmp_path, start=fetch_start.isoformat(),
                                          end=fetch_end.isoformat(), default_market=csv_market)
    ok = sum(1 for v in summary.values() if isinstance(v, int))
    errors = {k: v for k, v in summary.items() if isinstance(v, str)}
    if summary:
        st.sidebar.success(f"Fetched {ok}/{len(summary)} symbols.")
    if errors:
        with st.sidebar.expander(f"{len(errors)} error(s)"):
            for sym, err in errors.items():
                st.write(f"**{sym}**: {err}")

st.sidebar.divider()
db_symbols = get_db_symbols()
st.sidebar.caption(f"📁 {len(db_symbols)} symbol(s) currently in database")

# ---------------------------------------------------------------------------
# Main: backtest configuration
# ---------------------------------------------------------------------------
st.title("Backtest Configuration")

if not db_symbols:
    st.info("👈 No data yet. Use the sidebar to fetch some price history first "
             "(try a small preset universe with a limit of 10-25 to start quickly).")
    st.stop()

col1, col2 = st.columns([2, 1])

with col1:
    strategy_name = st.selectbox("Strategy", list(STRATEGY_REGISTRY.keys()))
    strategy_cls = STRATEGY_REGISTRY[strategy_name]

    st.markdown("**Parameters**")
    params = {}
    if strategy_cls.default_params:
        param_cols = st.columns(len(strategy_cls.default_params))
        for i, (pname, pdefault) in enumerate(strategy_cls.default_params.items()):
            help_text = strategy_cls.param_info.get(pname, "")
            with param_cols[i]:
                if isinstance(pdefault, float):
                    params[pname] = st.number_input(pname, value=float(pdefault), help=help_text)
                else:
                    params[pname] = st.number_input(pname, value=int(pdefault), step=1, help=help_text)
    else:
        st.caption("This strategy has no parameters.")

with col2:
    symbol_scope = st.radio("Run on", ["Specific symbols", "All US in DB", "All EU in DB", "Everything in DB"])
    chosen_symbols = None
    if symbol_scope == "Specific symbols":
        chosen_symbols = st.multiselect("Symbols", db_symbols, default=db_symbols[:min(5, len(db_symbols))])

st.markdown("**Backtest window & capital**")
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    bt_start = st.date_input("Start date", value=dt.date(2019, 1, 1), key="bt_start")
with c2:
    bt_end = st.date_input("End date", value=dt.date.today(), key="bt_end")
with c3:
    capital = st.number_input("Initial capital", min_value=100.0, value=10_000.0, step=1000.0)
with c4:
    commission = st.number_input("Commission % (per side)", min_value=0.0, value=0.10, step=0.05,
                                  help="e.g. 0.10 = 0.10%") / 100
with c5:
    slippage = st.number_input("Slippage % (per side)", min_value=0.0, value=0.05, step=0.05,
                                help="e.g. 0.05 = 0.05%") / 100

run_clicked = st.button("▶️ Run Backtest", type="primary", width='stretch')

# ---------------------------------------------------------------------------
# Run + show results
# ---------------------------------------------------------------------------
if run_clicked:
    if symbol_scope == "Specific symbols":
        symbols = chosen_symbols or []
    elif symbol_scope == "All US in DB":
        symbols = get_db_symbols("US")
    elif symbol_scope == "All EU in DB":
        symbols = get_db_symbols("EU")
    else:
        symbols = db_symbols

    if not symbols:
        st.warning("No symbols selected.")
        st.stop()

    with st.spinner(f"Backtesting {len(symbols)} symbol(s)..."):
        summary = run_backtest(
            symbols, strategy_name, params,
            start=bt_start.isoformat(), end=bt_end.isoformat(),
            initial_capital=capital, commission_pct=commission, slippage_pct=slippage,
        )
    st.session_state["last_run_id"] = summary["run_id"]
    st.session_state["last_run_results"] = summary["results"]
    st.session_state["last_run_symbols"] = symbols
    st.session_state["last_run_params"] = params
    st.session_state["last_run_strategy"] = strategy_name
    st.session_state["last_run_start"] = bt_start.isoformat()
    st.session_state["last_run_end"] = bt_end.isoformat()
    st.session_state["last_run_capital"] = capital
    st.session_state["last_run_commission"] = commission
    st.session_state["last_run_slippage"] = slippage

if "last_run_results" in st.session_state:
    st.divider()
    st.header(f"Results — Run #{st.session_state['last_run_id']}")

    results = st.session_state["last_run_results"]
    ok_results = {k: v for k, v in results.items() if isinstance(v, dict)}
    errors = {k: v for k, v in results.items() if isinstance(v, str)}

    if ok_results:
        df_results = pd.DataFrame(ok_results).T
        df_results.index.name = "Symbol"
        df_results = df_results.sort_values("total_return_pct", ascending=False)
        display_df = df_results[[
            "total_return_pct", "cagr_pct", "sharpe_ratio", "max_drawdown_pct",
            "win_rate_pct", "num_trades", "buy_hold_return_pct",
        ]].rename(columns={
            "total_return_pct": "Return %", "cagr_pct": "CAGR %", "sharpe_ratio": "Sharpe",
            "max_drawdown_pct": "Max DD %", "win_rate_pct": "Win Rate %",
            "num_trades": "# Trades", "buy_hold_return_pct": "Buy&Hold %",
        })
        st.dataframe(display_df.style.format({
            "Return %": "{:.2f}", "CAGR %": "{:.2f}", "Sharpe": "{:.2f}",
            "Max DD %": "{:.2f}", "Win Rate %": "{:.1f}", "Buy&Hold %": "{:.2f}",
        }), width='stretch')

        st.subheader("Chart a symbol")
        chart_symbol = st.selectbox("Pick a symbol to inspect", list(df_results.index))
        if chart_symbol:
            session = get_session()
            df = load_price_df(session, chart_symbol,
                                st.session_state["last_run_start"], st.session_state["last_run_end"])
            strat = get_strategy(st.session_state["last_run_strategy"], **st.session_state["last_run_params"])
            bt = run_single_backtest(df, strat, st.session_state["last_run_capital"],
                                      st.session_state["last_run_commission"],
                                      st.session_state["last_run_slippage"])
            stock = session.query(Stock).filter_by(symbol=chart_symbol).one()
            fig = plot_price_and_equity(chart_symbol, stock.name, df, bt,
                                         st.session_state["last_run_strategy"])
            st.pyplot(fig)

            if bt["trades"]:
                trade_df = pd.DataFrame(bt["trades"])[
                    ["entry_date", "entry_price", "exit_date", "exit_price", "pnl_pct"]
                ].rename(columns={
                    "entry_date": "Buy Date", "entry_price": "Buy Price",
                    "exit_date": "Sell Date", "exit_price": "Sell Price", "pnl_pct": "P&L %",
                })
                st.dataframe(trade_df.style.format({
                    "Buy Price": "{:.2f}", "Sell Price": "{:.2f}", "P&L %": "{:+.2f}",
                }), width='stretch')
            else:
                st.caption("No trades were triggered for this symbol in this window.")
            session.close()

    if errors:
        with st.expander(f"⚠️ {len(errors)} symbol(s) failed"):
            for sym, err in errors.items():
                st.write(f"**{sym}**: {err}")

# ---------------------------------------------------------------------------
# Past runs
# ---------------------------------------------------------------------------
st.divider()
with st.expander("📜 Past backtest runs"):
    session = get_session()
    runs = session.query(BacktestRun).order_by(BacktestRun.id.desc()).all()
    if runs:
        rows = [{
            "ID": r.id, "Strategy": r.strategy_name, "Params": r.params_json,
            "Start": r.start_date, "End": r.end_date, "# Stocks": len(r.results),
            "Created": r.created_at.strftime("%Y-%m-%d %H:%M"),
        } for r in runs]
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
    else:
        st.caption("No runs yet.")
    session.close()
