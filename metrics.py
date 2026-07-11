"""
Performance metrics computed from an equity curve / return series.
"""
import numpy as np
import pandas as pd

from config import TRADING_DAYS_PER_YEAR, RISK_FREE_RATE_ANNUAL


def total_return(equity: pd.Series) -> float:
    if len(equity) < 2 or equity.iloc[0] == 0:
        return 0.0
    return (equity.iloc[-1] / equity.iloc[0] - 1) * 100


def cagr(equity: pd.Series) -> float:
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0
    n_years = len(equity) / TRADING_DAYS_PER_YEAR
    if n_years <= 0:
        return 0.0
    ratio = equity.iloc[-1] / equity.iloc[0]
    if ratio <= 0:
        return -100.0
    return ((ratio ** (1 / n_years)) - 1) * 100


def annualized_volatility(daily_returns: pd.Series) -> float:
    if daily_returns.std() is None or len(daily_returns) < 2:
        return 0.0
    return daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR) * 100


def sharpe_ratio(daily_returns: pd.Series) -> float:
    if len(daily_returns) < 2 or daily_returns.std() == 0:
        return 0.0
    daily_rf = RISK_FREE_RATE_ANNUAL / TRADING_DAYS_PER_YEAR
    excess = daily_returns - daily_rf
    return (excess.mean() / daily_returns.std()) * np.sqrt(TRADING_DAYS_PER_YEAR)


def sortino_ratio(daily_returns: pd.Series) -> float:
    daily_rf = RISK_FREE_RATE_ANNUAL / TRADING_DAYS_PER_YEAR
    downside = daily_returns[daily_returns < 0]
    if len(downside) < 2 or downside.std() == 0:
        return 0.0
    excess = daily_returns.mean() - daily_rf
    return (excess / downside.std()) * np.sqrt(TRADING_DAYS_PER_YEAR)


def max_drawdown(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return drawdown.min() * 100


def calmar_ratio(cagr_pct: float, max_dd_pct: float) -> float:
    if max_dd_pct == 0:
        return 0.0
    return cagr_pct / abs(max_dd_pct)


def trade_stats(trades: list) -> dict:
    """trades: list of dicts with a 'pnl' key."""
    if not trades:
        return {"win_rate_pct": 0.0, "profit_factor": 0.0, "num_trades": 0}
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / len(pnls)) * 100 if pnls else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    return {
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor if np.isfinite(profit_factor) else 999.99,
        "num_trades": len(pnls),
    }
