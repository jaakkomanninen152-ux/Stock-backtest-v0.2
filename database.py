"""
Database layer: SQLAlchemy ORM models + session helpers.

Tables
------
stocks           - one row per ticker (symbol, market, exchange, currency ...)
price_bars       - daily OHLCV data per stock (unique on stock_id + date)
backtest_runs    - one row per backtest execution (strategy + params + date range)
backtest_results - one row per stock within a run (metrics)
trades           - individual simulated trades belonging to a backtest_result
"""
from datetime import datetime, date

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime,
    ForeignKey, UniqueConstraint, Text, Index
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from config import DATABASE_URL

Base = declarative_base()


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)  # yfinance ticker, e.g. AAPL, SAP.DE
    name = Column(String(200))
    market = Column(String(10))       # 'US' or 'EU'
    exchange = Column(String(50))     # e.g. NASDAQ, NYSE, XETRA, LSE, EURONEXT PARIS
    currency = Column(String(10))     # e.g. USD, EUR, GBP, CHF
    sector = Column(String(100))
    is_active = Column(Integer, default=1)

    price_bars = relationship("PriceBar", back_populates="stock", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Stock {self.symbol} ({self.market})>"


class PriceBar(Base):
    __tablename__ = "price_bars"

    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    adj_close = Column(Float)
    volume = Column(Float)

    stock = relationship("Stock", back_populates="price_bars")

    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_stock_date"),
        Index("ix_stock_date", "stock_id", "date"),
    )


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(Integer, primary_key=True)
    strategy_name = Column(String(100), nullable=False)
    params_json = Column(Text)        # JSON-encoded strategy parameters
    start_date = Column(Date)
    end_date = Column(Date)
    initial_capital = Column(Float)
    commission_pct = Column(Float)
    slippage_pct = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    results = relationship("BacktestResult", back_populates="run", cascade="all, delete-orphan")


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("backtest_runs.id"), nullable=False)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False)

    total_return_pct = Column(Float)
    cagr_pct = Column(Float)
    annual_vol_pct = Column(Float)
    sharpe_ratio = Column(Float)
    sortino_ratio = Column(Float)
    max_drawdown_pct = Column(Float)
    calmar_ratio = Column(Float)
    win_rate_pct = Column(Float)
    profit_factor = Column(Float)
    num_trades = Column(Integer)
    final_equity = Column(Float)
    buy_hold_return_pct = Column(Float)  # benchmark for the same period

    run = relationship("BacktestRun", back_populates="results")
    stock = relationship("Stock")
    trades = relationship("Trade", back_populates="result", cascade="all, delete-orphan")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    result_id = Column(Integer, ForeignKey("backtest_results.id"), nullable=False)
    entry_date = Column(Date)
    exit_date = Column(Date)
    entry_price = Column(Float)
    exit_price = Column(Float)
    side = Column(String(10))   # 'long' or 'short'
    pnl = Column(Float)
    pnl_pct = Column(Float)

    result = relationship("BacktestResult", back_populates="trades")


# ---------------------------------------------------------------------------
# Engine / session helpers
# ---------------------------------------------------------------------------
_engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def init_db():
    """Create all tables if they don't exist yet."""
    Base.metadata.create_all(_engine)


def get_session():
    return SessionLocal()
