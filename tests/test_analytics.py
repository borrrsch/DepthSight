# tests/test_analytics.py
"""
Tests for analytics CRUD functions: get_foundation_effectiveness_stats and get_market_sentiment.
"""

import pytest
from datetime import datetime, timezone
from api import crud, schemas


@pytest.mark.asyncio
async def test_create_trade_analytics_with_foundations(db_session, test_user):
    """Tests creating TradeAnalytics records with used_foundations."""
    analytics_data = schemas.TradeAnalyticsCreate(
        user_id=test_user.id,
        source_type="backtest",
        source_trade_id="test-trade-1",
        strategy_config_id=None,
        symbol="BTCUSDT",
        direction="LONG",
        timestamp_close=datetime.now(timezone.utc),
        pnl_usd=100.0,
        win_rate_contribution=1,  # Win
        profit_factor_gross_profit=100.0,
        profit_factor_gross_loss=0,
        used_foundations=["w_volume_cluster", "w_trend_break"],
        used_filters=["filter_adx"],
        used_management_blocks=["partial_tp"],
    )

    created = await crud.create_trade_analytics(db_session, analytics_data)
    await db_session.commit()

    assert created.id is not None
    assert created.source_type == "backtest"
    assert created.pnl_usd == 100.0
    assert created.used_foundations == ["w_volume_cluster", "w_trend_break"]


@pytest.mark.asyncio
async def test_create_trade_analytics_without_foundations(db_session, test_user):
    """Tests creating TradeAnalytics records with empty used_foundations."""
    analytics_data = schemas.TradeAnalyticsCreate(
        user_id=test_user.id,
        source_type="live",
        source_trade_id="test-trade-2",
        strategy_config_id=None,
        symbol="ETHUSDT",
        direction="SHORT",
        timestamp_close=datetime.now(timezone.utc),
        pnl_usd=-50.0,
        win_rate_contribution=-1,  # Loss
        profit_factor_gross_profit=0,
        profit_factor_gross_loss=50.0,
        used_foundations=[],  # Empty foundations
        used_filters=[],
        used_management_blocks=[],
    )

    created = await crud.create_trade_analytics(db_session, analytics_data)
    await db_session.commit()

    assert created.id is not None
    assert created.source_type == "live"
    assert created.used_foundations == []


@pytest.mark.asyncio
async def test_get_foundation_effectiveness_stats_with_data(db_session, test_user):
    """Tests that get_foundation_effectiveness_stats returns data correctly."""
    # Create test data with foundations
    for i in range(3):
        analytics_data = schemas.TradeAnalyticsCreate(
            user_id=test_user.id,
            source_type="backtest",
            source_trade_id=f"test-trade-stats-{i}",
            strategy_config_id=None,
            symbol="BTCUSDT",
            direction="LONG",
            timestamp_close=datetime.now(timezone.utc),
            pnl_usd=100.0 if i < 2 else -50.0,  # 2 wins, 1 loss
            win_rate_contribution=1 if i < 2 else -1,
            profit_factor_gross_profit=100.0 if i < 2 else 0,
            profit_factor_gross_loss=0 if i < 2 else 50.0,
            used_foundations=["w_volume_cluster"],  # Same foundation
            used_filters=[],
            used_management_blocks=[],
        )
        await crud.create_trade_analytics(db_session, analytics_data)

    await db_session.commit()

    # Get stats
    stats = await crud.get_foundation_effectiveness_stats(
        db_session, source_type="backtest"
    )

    assert len(stats) > 0

    # Find w_volume_cluster in stats
    volume_stat = next(
        (s for s in stats if s["foundation_id"] == "w_volume_cluster"), None
    )
    assert volume_stat is not None
    assert volume_stat["count"] == 3
    assert volume_stat["total_gross_profit"] == 200.0  # 100 + 100
    assert volume_stat["total_gross_loss"] == 50.0


@pytest.mark.asyncio
async def test_get_foundation_effectiveness_stats_empty_foundations(
    db_session, test_user
):
    """Tests that trades with empty foundations are counted as __no_foundation__."""
    # Create test data WITHOUT foundations
    analytics_data = schemas.TradeAnalyticsCreate(
        user_id=test_user.id,
        source_type="live",
        source_trade_id="test-trade-no-foundation",
        strategy_config_id=None,
        symbol="BTCUSDT",
        direction="LONG",
        timestamp_close=datetime.now(timezone.utc),
        pnl_usd=75.0,
        win_rate_contribution=1,
        profit_factor_gross_profit=75.0,
        profit_factor_gross_loss=0,
        used_foundations=[],  # Empty
        used_filters=[],
        used_management_blocks=[],
    )
    await crud.create_trade_analytics(db_session, analytics_data)
    await db_session.commit()

    # Get stats for live
    stats = await crud.get_foundation_effectiveness_stats(
        db_session, source_type="live"
    )

    assert len(stats) > 0

    # Should have __no_foundation__ entry
    no_foundation_stat = next(
        (s for s in stats if s["foundation_id"] == "__no_foundation__"), None
    )
    assert no_foundation_stat is not None
    assert no_foundation_stat["count"] == 1
    assert no_foundation_stat["total_gross_profit"] == 75.0


@pytest.mark.asyncio
async def test_get_market_sentiment_stats(db_session, test_user):
    """Tests that get_market_sentiment returns aggregated PnL by direction."""
    # Create LONG trades
    for i in range(2):
        analytics_data = schemas.TradeAnalyticsCreate(
            user_id=test_user.id,
            source_type="backtest",
            source_trade_id=f"test-trade-sentiment-long-{i}",
            strategy_config_id=None,
            symbol="BTCUSDT",
            direction="LONG",
            timestamp_close=datetime.now(timezone.utc),
            pnl_usd=100.0,
            win_rate_contribution=1,
            profit_factor_gross_profit=100.0,
            profit_factor_gross_loss=0,
            used_foundations=[],
            used_filters=[],
            used_management_blocks=[],
        )
        await crud.create_trade_analytics(db_session, analytics_data)

    # Create SHORT trades
    analytics_data = schemas.TradeAnalyticsCreate(
        user_id=test_user.id,
        source_type="backtest",
        source_trade_id="test-trade-sentiment-short",
        strategy_config_id=None,
        symbol="BTCUSDT",
        direction="SHORT",
        timestamp_close=datetime.now(timezone.utc),
        pnl_usd=-30.0,
        win_rate_contribution=-1,
        profit_factor_gross_profit=0,
        profit_factor_gross_loss=30.0,
        used_foundations=[],
        used_filters=[],
        used_management_blocks=[],
    )
    await crud.create_trade_analytics(db_session, analytics_data)

    await db_session.commit()

    # Get sentiment
    sentiment = await crud.get_market_sentiment(db_session, source_type="backtest")

    assert len(sentiment) == 2  # LONG and SHORT

    long_sentiment = next((s for s in sentiment if s["direction"] == "LONG"), None)
    short_sentiment = next((s for s in sentiment if s["direction"] == "SHORT"), None)

    assert long_sentiment is not None
    assert long_sentiment["total_pnl"] == 200.0  # 100 + 100

    assert short_sentiment is not None
    assert short_sentiment["total_pnl"] == -30.0


@pytest.mark.asyncio
async def test_get_foundation_stats_no_data(db_session):
    """Tests that get_foundation_effectiveness_stats returns empty list when no data."""
    stats = await crud.get_foundation_effectiveness_stats(
        db_session, source_type="backtest"
    )

    # Should return empty list, not error
    assert isinstance(stats, list)
    assert len(stats) == 0


@pytest.mark.asyncio
async def test_get_market_sentiment_no_data(db_session):
    """Tests that get_market_sentiment returns empty list when no data."""
    sentiment = await crud.get_market_sentiment(db_session, source_type="live")

    # Should return empty list, not error
    assert isinstance(sentiment, list)
    assert len(sentiment) == 0
