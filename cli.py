#!/usr/bin/env python3
"""
Command-line interface for the stock backtester.

Examples
--------
# 1. Fetch data
python cli.py fetch --symbols AAPL,MSFT,SAP.DE,ASML.AS --start 2018-01-01
python cli.py fetch --universe US --limit 50 --start 2015-01-01
python cli.py fetch --universe EU --start 2015-01-01
python cli.py fetch --universe ALL --start 2015-01-01

# 1b. Fetch one specific exchange, e.g. all curated Nasdaq Helsinki (OMXH) tickers
python cli.py list-exchanges
python cli.py fetch --exchange NASDAQ_HELSINKI --start 2015-01-01

# 1c. Fetch every NASDAQ-listed US stock (~3-4.5k tickers, not just S&P 500)
python cli.py fetch --universe NASDAQ_FULL --limit 50 --start 2020-01-01

# 1d. Fetch a fully custom/complete ticker list from your own CSV
python cli.py fetch --csv my_omxh_tickers.csv --csv-market EU --start 2015-01-01

# 2. See what's in the DB
python cli.py list-stocks
python cli.py list-stocks --market EU

# 3. Run a backtest
python cli.py backtest --strategy sma_cross --params fast=20,slow=100 \
    --symbols AAPL,MSFT,SAP.DE --start 2018-01-01

python cli.py backtest --strategy rsi_mean_reversion --params period=14,oversold=30,overbought=60 \
    --market EU --start 2018-01-01

# 4. Inspect / report
python cli.py runs
python cli.py results --run-id 1
python cli.py report --run-id 1 --top 10
"""
import argparse
import sys
import json

from database import get_session, Stock, BacktestRun, BacktestResult, init_db
from data_fetcher import fetch_and_store, fetch_universe, fetch_exchange, fetch_from_csv
from tickers import get_universe, list_exchanges
from strategies import STRATEGY_REGISTRY
from backtester import run_backtest
from reporting import generate_run_report

try:
    from tabulate import tabulate
except ImportError:
    tabulate = None


def _print_table(headers, rows):
    if tabulate:
        print(tabulate(rows, headers=headers, floatfmt=".2f"))
    else:
        print(" | ".join(headers))
        for row in rows:
            print(" | ".join(str(c) for c in row))


def _progress(symbol, i, total, status):
    print(f"  [{i}/{total}] {symbol}: {status}")


def _parse_params(params_str: str) -> dict:
    """'fast=20,slow=100' -> {'fast': 20, 'slow': 100} (numbers auto-cast)"""
    if not params_str:
        return {}
    out = {}
    for pair in params_str.split(","):
        k, v = pair.split("=")
        k, v = k.strip(), v.strip()
        try:
            v = int(v)
        except ValueError:
            try:
                v = float(v)
            except ValueError:
                pass
        out[k] = v
    return out


def cmd_fetch(args):
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
        universe = get_universe("ALL")
        meta = {s: universe[s] for s in symbols if s in universe}
        print(f"Fetching {len(symbols)} symbol(s)...")
        summary = fetch_and_store(symbols, start=args.start, end=args.end,
                                   meta=meta, progress_cb=_progress)
    elif args.exchange:
        print(f"Fetching exchange '{args.exchange}' (limit={args.limit})...")
        summary = fetch_exchange(args.exchange, start=args.start, end=args.end,
                                  limit=args.limit, progress_cb=_progress)
    elif args.csv:
        print(f"Fetching tickers from CSV '{args.csv}' (limit={args.limit})...")
        summary = fetch_from_csv(args.csv, start=args.start, end=args.end,
                                  default_market=args.csv_market, limit=args.limit,
                                  progress_cb=_progress)
    else:
        print(f"Fetching '{args.universe}' universe (limit={args.limit})...")
        summary = fetch_universe(args.universe, start=args.start, end=args.end,
                                  limit=args.limit, progress_cb=_progress)

    ok = sum(1 for v in summary.values() if isinstance(v, int))
    errors = {k: v for k, v in summary.items() if isinstance(v, str)}
    print(f"\nDone. {ok}/{len(summary)} symbols fetched successfully.")
    if errors:
        print(f"{len(errors)} error(s):")
        for sym, err in errors.items():
            print(f"  {sym}: {err}")


def cmd_list_exchanges(args):
    exchanges = list_exchanges()
    rows = [(code, count) for code, count in sorted(exchanges.items())]
    _print_table(["Exchange code", "# curated tickers"], rows)
    print("\nUse: python cli.py fetch --exchange <code> --start YYYY-MM-DD")
    print("Note: these are curated liquid names, not necessarily every listed company.")
    print("For a fully complete listing, use: python cli.py fetch --csv path/to/list.csv")


def cmd_list_stocks(args):
    session = get_session()
    init_db()
    q = session.query(Stock)
    if args.market:
        q = q.filter_by(market=args.market.upper())
    stocks = q.order_by(Stock.market, Stock.symbol).all()
    rows = [(s.symbol, s.name, s.market, s.exchange, s.currency,
             len(s.price_bars)) for s in stocks]
    _print_table(["Symbol", "Name", "Market", "Exchange", "Ccy", "#Bars"], rows)
    print(f"\n{len(stocks)} stock(s) in database.")
    session.close()


def cmd_list_strategies(args):
    rows = []
    for name, cls in STRATEGY_REGISTRY.items():
        params = ", ".join(f"{k}: {v}" for k, v in cls.param_info.items()) or "(none)"
        rows.append((name, params))
    _print_table(["Strategy", "Parameters"], rows)


def cmd_backtest(args):
    session = get_session()
    init_db()

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]
    elif args.market:
        q = session.query(Stock).filter_by(market=args.market.upper())
        symbols = [s.symbol for s in q.all()]
        if not symbols:
            print(f"No stocks for market '{args.market}' in DB yet. Run `fetch` first.")
            return
    else:
        symbols = [s.symbol for s in session.query(Stock).all()]
        if not symbols:
            print("Database is empty. Run `fetch` first.")
            return
    session.close()

    params = _parse_params(args.params)
    print(f"Running strategy '{args.strategy}' with params {params} over {len(symbols)} symbol(s)...")

    summary = run_backtest(
        symbols, args.strategy, params,
        start=args.start, end=args.end,
        initial_capital=args.capital,
        commission_pct=args.commission,
        slippage_pct=args.slippage,
        progress_cb=_progress,
    )

    run_id = summary["run_id"]
    results = summary["results"]
    ok_results = {k: v for k, v in results.items() if isinstance(v, dict)}
    errors = {k: v for k, v in results.items() if isinstance(v, str)}

    print(f"\nBacktest run #{run_id} complete. {len(ok_results)} succeeded, {len(errors)} failed.")
    if ok_results:
        ranked = sorted(ok_results.items(), key=lambda kv: kv[1]["total_return_pct"], reverse=True)
        rows = [(sym, f"{m['total_return_pct']:.2f}%", f"{m['cagr_pct']:.2f}%",
                 f"{m['sharpe_ratio']:.2f}", f"{m['max_drawdown_pct']:.2f}%",
                 f"{m['win_rate_pct']:.1f}%", m["num_trades"],
                 f"{m['buy_hold_return_pct']:.2f}%")
                for sym, m in ranked[:25]]
        _print_table(["Symbol", "Return", "CAGR", "Sharpe", "MaxDD", "WinRate", "#Trades", "Buy&Hold"], rows)
        if len(ranked) > 25:
            print(f"... and {len(ranked) - 25} more. Use `python cli.py results --run-id {run_id}` to see all.")
    if errors:
        print("\nErrors:")
        for sym, err in errors.items():
            print(f"  {sym}: {err}")

    print(f"\nTip: python cli.py report --run-id {run_id}")


def cmd_runs(args):
    session = get_session()
    init_db()
    runs = session.query(BacktestRun).order_by(BacktestRun.id.desc()).all()
    rows = [(r.id, r.strategy_name, r.params_json, r.start_date, r.end_date,
              len(r.results), r.created_at.strftime("%Y-%m-%d %H:%M")) for r in runs]
    _print_table(["ID", "Strategy", "Params", "Start", "End", "#Stocks", "Created"], rows)
    session.close()


def cmd_results(args):
    session = get_session()
    init_db()
    q = (session.query(BacktestResult)
         .filter_by(run_id=args.run_id)
         .order_by(BacktestResult.total_return_pct.desc()))
    results = q.all()
    if not results:
        print(f"No results for run {args.run_id}.")
        return
    rows = []
    for r in results:
        rows.append((
            r.stock.symbol, r.stock.market, f"{r.total_return_pct:.2f}%",
            f"{r.cagr_pct:.2f}%", f"{r.sharpe_ratio:.2f}", f"{r.sortino_ratio:.2f}",
            f"{r.max_drawdown_pct:.2f}%", f"{r.calmar_ratio:.2f}",
            f"{r.win_rate_pct:.1f}%", f"{r.profit_factor:.2f}", r.num_trades,
            f"{r.buy_hold_return_pct:.2f}%",
        ))
    _print_table(["Symbol", "Mkt", "Return", "CAGR", "Sharpe", "Sortino",
                  "MaxDD", "Calmar", "WinRate", "PF", "#Trades", "Buy&Hold"], rows)
    session.close()


def cmd_report(args):
    path = generate_run_report(args.run_id, top_n=args.top)
    print(f"Report written to: {path}")
    print("Open it in a browser to view ranked results and equity-curve charts.")


def build_parser():
    p = argparse.ArgumentParser(description="Stock backtesting toolkit (US + European markets)")
    sub = p.add_subparsers(dest="command", required=True)

    f = sub.add_parser("fetch", help="Download & store price history")
    f.add_argument("--symbols", help="Comma-separated tickers, e.g. AAPL,SAP.DE")
    f.add_argument("--universe", choices=["US", "EU", "ALL", "NASDAQ_FULL"], default="ALL",
                    help="Preset universe to fetch if --symbols not given. "
                         "NASDAQ_FULL = every Nasdaq-listed security (~3-4.5k tickers, slow)")
    f.add_argument("--exchange", default=None,
                    help="Fetch a single curated exchange, e.g. NASDAQ_HELSINKI "
                         "(see `python cli.py list-exchanges`)")
    f.add_argument("--csv", default=None,
                    help="Path to a CSV file with a 'symbol' column (and optionally "
                         "name/exchange/currency/sector) for a fully custom/complete ticker list")
    f.add_argument("--csv-market", default="EU", choices=["US", "EU"],
                    help="Market label to assign to tickers loaded via --csv if not inferable")
    f.add_argument("--limit", type=int, default=None, help="Cap number of tickers (testing)")
    f.add_argument("--start", default="2015-01-01")
    f.add_argument("--end", default=None)
    f.set_defaults(func=cmd_fetch)

    le = sub.add_parser("list-exchanges", help="List available curated exchange codes")
    le.set_defaults(func=cmd_list_exchanges)

    ls = sub.add_parser("list-stocks", help="List stocks currently in the database")
    ls.add_argument("--market", choices=["US", "EU"], default=None)
    ls.set_defaults(func=cmd_list_stocks)

    lst = sub.add_parser("list-strategies", help="List available strategies and their parameters")
    lst.set_defaults(func=cmd_list_strategies)

    bt = sub.add_parser("backtest", help="Run a strategy over one or more stocks")
    bt.add_argument("--strategy", required=True, choices=list(STRATEGY_REGISTRY.keys()))
    bt.add_argument("--params", default="", help="e.g. fast=20,slow=100")
    bt.add_argument("--symbols", default=None, help="Comma-separated tickers")
    bt.add_argument("--market", choices=["US", "EU"], default=None,
                     help="Run over all stocks of this market currently in the DB")
    bt.add_argument("--start", default=None)
    bt.add_argument("--end", default=None)
    bt.add_argument("--capital", type=float, default=10_000.0)
    bt.add_argument("--commission", type=float, default=0.001)
    bt.add_argument("--slippage", type=float, default=0.0005)
    bt.set_defaults(func=cmd_backtest)

    rn = sub.add_parser("runs", help="List past backtest runs")
    rn.set_defaults(func=cmd_runs)

    rs = sub.add_parser("results", help="Show detailed results for one run")
    rs.add_argument("--run-id", type=int, required=True)
    rs.set_defaults(func=cmd_results)

    rp = sub.add_parser("report", help="Generate an HTML report with equity-curve charts")
    rp.add_argument("--run-id", type=int, required=True)
    rp.add_argument("--top", type=int, default=10, help="Number of top performers to chart")
    rp.set_defaults(func=cmd_report)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
