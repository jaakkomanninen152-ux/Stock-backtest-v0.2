"""
Core backtest engine.

Approach: vectorized, event-derived. The strategy produces a target
position series (1 = long, 0 = flat). We shift it by one bar so that a
signal computed from day T's close is only acted on from day T+1 onward
(no look-ahead). Trades (entries/exits) are then reconstructed from the
position changes so we can report win rate, profit factor, and a trade
log, while commission + slippage are charged on each position change.
"""
from __future__ import annotations
import json
import datetime as dt
from typing import Optional, List, Dict

import numpy as np
import pandas as pd

from database import get_session, Stock, PriceBar, BacktestRun, BacktestResult, Trade, init_db
from strategies import get_strategy, Strategy
import metrics as M
from config import (
    DEFAULT_INITIAL_CAPITAL, DEFAULT_COMMISSION_PCT, DEFAULT_SLIPPAGE_PCT
)


def load_price_df(session, symbol: str, start: Optional[str] = None,
                   end: Optional[str] = None) -> Optional[pd.DataFrame]:
    stock = session.query(Stock).filter_by(symbol=symbol).one_or_none()
    if stock is None:
        return None
    q = session.query(PriceBar).filter_by(stock_id=stock.id).order_by(PriceBar.date)
    if start:
        q = q.filter(PriceBar.date >= dt.date.fromisoformat(start))
    if end:
        q = q.filter(PriceBar.date <= dt.date.fromisoformat(end))
    rows = q.all()
    if not rows:
        return None
    df = pd.DataFrame([{
        "date": r.date, "open": r.open, "high": r.high, "low": r.low,
        "close": r.close, "adj_close": r.adj_close, "volume": r.volume,
    } for r in rows])
    df = df.set_index("date")
    # Use adjusted close for return calculations to correctly account for
    # dividends/splits, falling back to close if adj_close is missing.
    df["close"] = df["adj_close"].fillna(df["close"])
    df = df.dropna(subset=["close"])
    return df


def _reconstruct_trades(df: pd.DataFrame, position: pd.Series,
                         commission_pct: float, slippage_pct: float) -> List[Dict]:
    """
    Rebuilds a discrete trade log from a (shifted) position series.
    Only supports long/flat (0/1) positions.
    """
    trades = []
    in_trade = False
    entry_date = entry_price = None
    cost_pct = commission_pct + slippage_pct

    prev_pos = 0
    for date, pos in position.items():
        price = df.loc[date, "close"]
        if pos == 1 and prev_pos == 0 and not in_trade:
            entry_date = date
            entry_price = price * (1 + cost_pct)  # pay slippage+commission on entry
            in_trade = True
        elif pos == 0 and prev_pos == 1 and in_trade:
            exit_price = price * (1 - cost_pct)  # pay slippage+commission on exit
            pnl = exit_price - entry_price
            pnl_pct = (pnl / entry_price) * 100 if entry_price else 0
            trades.append({
                "entry_date": entry_date, "exit_date": date,
                "entry_price": entry_price, "exit_price": exit_price,
                "side": "long", "pnl": pnl, "pnl_pct": pnl_pct,
            })
            in_trade = False
        prev_pos = pos

    # close any open trade at the last available price (mark-to-market)
    if in_trade:
        last_date = df.index[-1]
        exit_price = df.loc[last_date, "close"] * (1 - cost_pct)
        pnl = exit_price - entry_price
        pnl_pct = (pnl / entry_price) * 100 if entry_price else 0
        trades.append({
            "entry_date": entry_date, "exit_date": last_date,
            "entry_price": entry_price, "exit_price": exit_price,
            "side": "long", "pnl": pnl, "pnl_pct": pnl_pct,
        })
    return trades


def run_single_backtest(df: pd.DataFrame, strategy: Strategy,
                         initial_capital: float = DEFAULT_INITIAL_CAPITAL,
                         commission_pct: float = DEFAULT_COMMISSION_PCT,
                         slippage_pct: float = DEFAULT_SLIPPAGE_PCT) -> dict:
    """
    Runs one strategy over one stock's price history.
    Returns a dict with the equity curve, metrics, and trade log.
    """
    if df is None or len(df) < 30:
        raise ValueError("Not enough price history to backtest (need >= 30 bars)")

    raw_signal = strategy.generate_signals(df)
    # Shift by 1 to avoid look-ahead: act on yesterday's signal today.
    position = raw_signal.shift(1).fillna(0)
    position = position.clip(-1, 1)  # engine below only truly supports 0/1 for long-only P&L

    daily_ret = df["close"].pct_change().fillna(0)
    strat_ret = position * daily_ret

    # Charge transaction costs whenever position changes (entry or exit)
    turnover = position.diff().abs().fillna(0)
    cost_pct = commission_pct + slippage_pct
    strat_ret = strat_ret - turnover * cost_pct

    equity = (1 + strat_ret).cumprod() * initial_capital
    equity.iloc[0] = initial_capital

    bh_equity = (1 + daily_ret).cumprod() * initial_capital
    bh_equity.iloc[0] = initial_capital

    trades = _reconstruct_trades(df, position, commission_pct, slippage_pct)
    tstats = M.trade_stats(trades)

    cagr_pct = M.cagr(equity)
    mdd_pct = M.max_drawdown(equity)

    result = {
        "equity_curve": equity,
        "benchmark_curve": bh_equity,
        "trades": trades,
        "metrics": {
            "total_return_pct": M.total_return(equity),
            "cagr_pct": cagr_pct,
            "annual_vol_pct": M.annualized_volatility(strat_ret),
            "sharpe_ratio": M.sharpe_ratio(strat_ret),
            "sortino_ratio": M.sortino_ratio(strat_ret),
            "max_drawdown_pct": mdd_pct,
            "calmar_ratio": M.calmar_ratio(cagr_pct, mdd_pct),
            "win_rate_pct": tstats["win_rate_pct"],
            "profit_factor": tstats["profit_factor"],
            "num_trades": tstats["num_trades"],
            "final_equity": float(equity.iloc[-1]),
            "buy_hold_return_pct": M.total_return(bh_equity),
        },
    }
    return result


def run_backtest(symbols: List[str], strategy_name: str, strategy_params: Optional[dict] = None,
                  start: Optional[str] = None, end: Optional[str] = None,
                  initial_capital: float = DEFAULT_INITIAL_CAPITAL,
                  commission_pct: float = DEFAULT_COMMISSION_PCT,
                  slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
                  persist: bool = True, progress_cb=None) -> dict:
    """
    Runs a strategy across many symbols, persists a BacktestRun + one
    BacktestResult per symbol (+ trades) to the database, and returns a
    summary {run_id, results: {symbol: metrics dict or error string}}.
    """
    init_db()
    session = get_session()
    strategy_params = strategy_params or {}
    strategy = get_strategy(strategy_name, **strategy_params)

    run = None
    if persist:
        run = BacktestRun(
            strategy_name=strategy_name,
            params_json=json.dumps(strategy_params),
            start_date=dt.date.fromisoformat(start) if start else None,
            end_date=dt.date.fromisoformat(end) if end else None,
            initial_capital=initial_capital,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
        )
        session.add(run)
        session.commit()

    results = {}
    try:
        for i, symbol in enumerate(symbols, start=1):
            try:
                df = load_price_df(session, symbol, start, end)
                if df is None or df.empty:
                    results[symbol] = "ERROR: no price data in DB (fetch it first)"
                    if progress_cb:
                        progress_cb(symbol, i, len(symbols), "no data")
                    continue

                bt = run_single_backtest(df, strategy, initial_capital, commission_pct, slippage_pct)
                results[symbol] = bt["metrics"]

                if persist:
                    stock = session.query(Stock).filter_by(symbol=symbol).one()
                    br = BacktestResult(
                        run_id=run.id, stock_id=stock.id,
                        **bt["metrics"],
                    )
                    session.add(br)
                    session.commit()
                    for t in bt["trades"]:
                        session.add(Trade(result_id=br.id, **t))
                    session.commit()

                if progress_cb:
                    progress_cb(symbol, i, len(symbols),
                                f"return={bt['metrics']['total_return_pct']:.1f}%")
            except Exception as exc:
                session.rollback()
                results[symbol] = f"ERROR: {exc}"
                if progress_cb:
                    progress_cb(symbol, i, len(symbols), f"error: {exc}")
    finally:
        session.close()

    return {"run_id": run.id if run else None, "results": results}
