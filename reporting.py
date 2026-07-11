"""
Generates simple visual reports (equity curve charts + an HTML summary page)
for a completed backtest run.

Charts are embedded directly into the HTML as base64 data URIs (rather than
saved as separate PNG files and linked by relative path). This makes the
single report.html file fully self-contained and portable -- it renders
correctly whether opened directly in a browser, downloaded, emailed, or
displayed inline in a notebook environment like Google Colab/Jupyter, where
relative-path images often fail to resolve.
"""
import os
import json
import base64
import io
import datetime as dt

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure

from database import get_session, BacktestRun, BacktestResult, Stock
from backtester import load_price_df, run_single_backtest
from strategies import get_strategy
from config import REPORTS_DIR


def generate_run_report(run_id: int, top_n: int = 10) -> str:
    """
    Builds an HTML report ranking all stocks in a run by total return, with
    equity-curve charts for the top N performers. Returns the report path.
    """
    session = get_session()
    run = session.query(BacktestRun).filter_by(id=run_id).one_or_none()
    if run is None:
        raise ValueError(f"No backtest run with id={run_id}")

    results = (
        session.query(BacktestResult)
        .filter_by(run_id=run_id)
        .order_by(BacktestResult.total_return_pct.desc())
        .all()
    )
    if not results:
        raise ValueError(f"Run {run_id} has no results")

    run_dir = os.path.join(REPORTS_DIR, f"run_{run_id}")
    os.makedirs(run_dir, exist_ok=True)

    params = json.loads(run.params_json or "{}")
    strategy = get_strategy(run.strategy_name, **params)

    chart_data_uris = {}
    trades_html_by_symbol = {}
    for r in results[:top_n]:
        stock = session.query(Stock).filter_by(id=r.stock_id).one()
        df = load_price_df(session, stock.symbol,
                            run.start_date.isoformat() if run.start_date else None,
                            run.end_date.isoformat() if run.end_date else None)
        if df is None:
            continue
        bt = run_single_backtest(df, strategy, run.initial_capital,
                                  run.commission_pct, run.slippage_pct)
        trades = bt["trades"]

        # Two panels: price chart with buy/sell markers on top, equity curve
        # vs. buy-and-hold benchmark underneath, sharing the same x-axis.
        fig = Figure(figsize=(9, 7))
        (ax_price, ax_equity) = fig.subplots(
            2, 1, sharex=True, gridspec_kw={"height_ratios": [1.3, 1]},
        )

        ax_price.plot(df.index, df["close"], color="#555", linewidth=1, label="Price")
        if trades:
            buy_dates = [t["entry_date"] for t in trades]
            buy_prices = [df.loc[t["entry_date"], "close"] for t in trades]
            sell_dates = [t["exit_date"] for t in trades]
            sell_prices = [df.loc[t["exit_date"], "close"] for t in trades]
            ax_price.scatter(buy_dates, buy_prices, marker="^", color="#2ecc71",
                              s=90, zorder=5, edgecolors="black", linewidths=0.5, label="Buy")
            ax_price.scatter(sell_dates, sell_prices, marker="v", color="#e74c3c",
                              s=90, zorder=5, edgecolors="black", linewidths=0.5, label="Sell")
        ax_price.set_title(f"{stock.symbol} — {stock.name}")
        ax_price.set_ylabel("Price")
        ax_price.legend(loc="upper left", fontsize=8)

        ax_equity.plot(bt["equity_curve"].index, bt["equity_curve"].values,
                        label=f"{run.strategy_name}", linewidth=1.8)
        ax_equity.plot(bt["benchmark_curve"].index, bt["benchmark_curve"].values,
                        label="Buy & Hold", linewidth=1.2, linestyle="--", alpha=0.7)
        ax_equity.set_ylabel("Equity")
        ax_equity.legend(loc="upper left", fontsize=8)
        fig.tight_layout()

        # Encode the chart as a base64 PNG data URI so it's embedded directly
        # in the HTML -- no separate file, no relative-path resolution needed.
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110)
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode("ascii")
        chart_data_uris[stock.symbol] = f"data:image/png;base64,{encoded}"

        # Trade log table: exact buy/sell dates, prices, and P&L per trade.
        if trades:
            trade_rows = "".join(f"""
            <tr>
              <td>{i + 1}</td>
              <td>{t['entry_date']}</td>
              <td>{t['entry_price']:.2f}</td>
              <td>{t['exit_date']}</td>
              <td>{t['exit_price']:.2f}</td>
              <td class="{'pos' if t['pnl'] >= 0 else 'neg'}">{t['pnl_pct']:+.2f}%</td>
            </tr>""" for i, t in enumerate(trades))
            trades_html_by_symbol[stock.symbol] = f"""
            <table class="trades">
            <tr><th>#</th><th>Buy Date</th><th>Buy Price</th><th>Sell Date</th><th>Sell Price</th><th>P&amp;L</th></tr>
            {trade_rows}
            </table>"""
        else:
            trades_html_by_symbol[stock.symbol] = "<p><i>No trades were triggered in this period.</i></p>"

    # Build HTML
    rows_html = ""
    for r in results:
        stock = session.query(Stock).filter_by(id=r.stock_id).one()
        rows_html += f"""
        <tr>
          <td>{stock.symbol}</td>
          <td>{stock.name}</td>
          <td>{stock.market}</td>
          <td>{r.total_return_pct:.2f}%</td>
          <td>{r.cagr_pct:.2f}%</td>
          <td>{r.sharpe_ratio:.2f}</td>
          <td>{r.max_drawdown_pct:.2f}%</td>
          <td>{r.win_rate_pct:.1f}%</td>
          <td>{r.num_trades}</td>
          <td>{r.buy_hold_return_pct:.2f}%</td>
        </tr>"""

    charts_html = "".join(
        f'<h3>{sym}</h3>'
        f'<img src="{data_uri}" style="max-width:100%;border:1px solid #ddd;">'
        f'{trades_html_by_symbol.get(sym, "")}'
        f'<div style="margin-bottom:36px;"></div>'
        for sym, data_uri in chart_data_uris.items()
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Backtest Report — Run {run_id}</title>
<style>
 body {{ font-family: -apple-system, Arial, sans-serif; margin: 32px; color: #1a1a1a; background:#fafafa;}}
 table {{ border-collapse: collapse; width: 100%; margin-bottom: 32px; background:#fff;}}
 th, td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: right; font-size: 14px;}}
 th {{ background: #2c3e50; color: white; position: sticky; top:0;}}
 td:nth-child(1), td:nth-child(2), td:nth-child(3) {{ text-align: left; }}
 h1 {{ color: #2c3e50; }}
 .meta {{ color: #555; margin-bottom: 24px; }}
 table.trades {{ width: auto; min-width: 480px; margin-top: 8px; margin-bottom: 8px; }}
 table.trades th {{ background: #7f8c8d; }}
 table.trades td.pos {{ color: #1e8e3e; font-weight: 600; }}
 table.trades td.neg {{ color: #d93025; font-weight: 600; }}
</style></head>
<body>
<h1>Backtest Report — Run #{run_id}</h1>
<div class="meta">
  Strategy: <b>{run.strategy_name}</b> {params} <br>
  Period: {run.start_date} → {run.end_date} <br>
  Initial capital: {run.initial_capital:,.2f} | Commission: {run.commission_pct*100:.2f}% | Slippage: {run.slippage_pct*100:.2f}% <br>
  Generated: {dt.datetime.now().isoformat(timespec='seconds')}
</div>
<h2>Ranked Results ({len(results)} stocks)</h2>
<table>
<tr><th>Symbol</th><th>Name</th><th>Market</th><th>Total Return</th><th>CAGR</th>
<th>Sharpe</th><th>Max DD</th><th>Win Rate</th><th># Trades</th><th>Buy&amp;Hold Return</th></tr>
{rows_html}
</table>
<h2>Top {min(top_n, len(chart_data_uris))} Equity Curves &amp; Trade Signals</h2>
<p style="color:#555;">Green ▲ = buy (entry), red ▼ = sell (exit), plotted on the price series. The trade log below each chart lists the exact dates, prices, and P&amp;L for every simulated trade.</p>
{charts_html}
</body></html>
"""
    report_path = os.path.join(run_dir, "report.html")
    with open(report_path, "w") as f:
        f.write(html)

    session.close()
    return report_path
