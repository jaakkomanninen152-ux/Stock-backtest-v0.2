"""
Central configuration for the backtester.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "market_data.sqlite3")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

# Trading assumptions used by the backtest engine
DEFAULT_COMMISSION_PCT = 0.001   # 0.1% per trade (each side)
DEFAULT_SLIPPAGE_PCT = 0.0005    # 0.05% per trade (each side)
DEFAULT_INITIAL_CAPITAL = 10_000.0
RISK_FREE_RATE_ANNUAL = 0.02     # used for Sharpe ratio
TRADING_DAYS_PER_YEAR = 252
