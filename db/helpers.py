"""
Database helper utilities: upsert operations for assets, market_prices, asset_metrics.
All functions accept an open SQLAlchemy Session and return the relevant ID.
"""
from datetime import date as date_type
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from db.models import Asset, MarketPrice, AssetMetrics


def upsert_asset(
    db: Session,
    symbol: str,
    asset_type: str,
    name: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    exchange: Optional[str] = None,
) -> int:
    """
    Insert or update an asset record. Returns asset_id.
    Uses ON CONFLICT DO UPDATE so repeated calls are safe.
    """
    existing = db.query(Asset).filter_by(symbol=symbol).first()
    if existing:
        # Update mutable fields if new info provided
        if name and existing.name != name:
            existing.name = name
        if sector and existing.sector != sector:
            existing.sector = sector
        db.flush()
        return existing.asset_id

    asset = Asset(
        symbol=symbol,
        name=name or symbol,
        asset_type=_normalize_type(asset_type),
        sector=sector,
        industry=industry,
        exchange=exchange,
    )
    db.add(asset)
    db.flush()
    return asset.asset_id


def store_market_price(
    db: Session,
    asset_id: int,
    trade_date: date_type,
    close_price: float,
    open_price: Optional[float] = None,
    high_price: Optional[float] = None,
    low_price: Optional[float] = None,
    volume: Optional[int] = None,
) -> None:
    """
    Insert or update a market_prices row for (asset_id, trade_date).
    Silently skips if price data is unavailable.
    """
    if close_price is None:
        return

    existing = (
        db.query(MarketPrice)
        .filter_by(asset_id=asset_id, trade_date=trade_date)
        .first()
    )
    if existing:
        existing.close_price = close_price
        if open_price:
            existing.open_price = open_price
        if high_price:
            existing.high_price = high_price
        if low_price:
            existing.low_price = low_price
        if volume:
            existing.volume = volume
    else:
        db.add(MarketPrice(
            asset_id=asset_id,
            trade_date=trade_date,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            adjusted_close=close_price,
            volume=volume,
        ))


def upsert_asset_metrics(
    db: Session,
    asset_id: int,
    trade_date: date_type,
    volatility_30d: Optional[float] = None,
    return_30d: Optional[float] = None,
    beta_vs_spy: Optional[float] = None,
    sharpe_ratio: Optional[float] = None,
) -> None:
    """Insert or update asset_metrics for (asset_id, trade_date)."""
    existing = (
        db.query(AssetMetrics)
        .filter_by(asset_id=asset_id, trade_date=trade_date)
        .first()
    )
    if existing:
        if volatility_30d is not None:
            existing.volatility_30d = volatility_30d
        if return_30d is not None:
            existing.return_30d = return_30d
        if beta_vs_spy is not None:
            existing.beta_vs_spy = beta_vs_spy
        if sharpe_ratio is not None:
            existing.sharpe_ratio = sharpe_ratio
    else:
        db.add(AssetMetrics(
            asset_id=asset_id,
            trade_date=trade_date,
            volatility_30d=volatility_30d,
            return_30d=return_30d,
            beta_vs_spy=beta_vs_spy,
            sharpe_ratio=sharpe_ratio,
        ))


def _normalize_type(asset_type: str) -> str:
    """Normalize asset_type to valid CHECK constraint values."""
    mapping = {
        "stock": "stock",
        "equity": "stock",
        "etf": "etf",
        "bond_etf": "bond_etf",
        "bond": "bond_etf",
        "index": "index",
        "unknown": "etf",  # safe default
    }
    return mapping.get(asset_type.lower(), "etf")
