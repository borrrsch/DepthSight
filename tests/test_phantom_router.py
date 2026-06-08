from datetime import datetime, timedelta, timezone

import pytest

from api import models


pytestmark = pytest.mark.asyncio


def _phantom_trade(
    user_id: int, suffix: str, status: str, pnl: float
) -> models.PhantomTrade:
    now = datetime.now(timezone.utc)
    return models.PhantomTrade(
        user_id=user_id,
        real_trade_id=f"trade-{suffix}",
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=100.0,
        entry_time=now - timedelta(hours=3),
        initial_stop_loss=95.0,
        initial_take_profit=115.0,
        be_trigger_time=now - timedelta(hours=2),
        be_exit_price=100.1,
        real_pnl_pct=0.0,
        real_pnl_usd=0.0,
        phantom_status=status,
        phantom_exit_time=now - timedelta(hours=1),
        phantom_exit_price=115.0 if status == "TP_HIT" else 95.0,
        phantom_pnl_pct=pnl,
        phantom_pnl_usd=pnl * 10,
        mfe_after_be=4.0 if status == "TP_HIT" else 1.0,
        mae_after_be=0.5 if status == "TP_HIT" else 3.0,
        candles_to_resolution=8,
        timeout_candles=20,
    )


async def test_phantom_stats_uses_timedelta_window_and_user_scope(
    authenticated_client,
    pro_user,
    db_session,
    free_user,
):
    db_session.add_all(
        [
            _phantom_trade(pro_user.id, "tp", "TP_HIT", 2.5),
            _phantom_trade(pro_user.id, "sl", "SL_HIT", -1.0),
            _phantom_trade(free_user.id, "other", "TP_HIT", 9.0),
        ]
    )
    await db_session.commit()

    response = await authenticated_client.get("/api/v1/analytics/phantom/stats?days=30")

    assert response.status_code == 200
    data = response.json()
    assert data["totalBeTrades"] == 2
    assert data["tpWouldHit"] == 1
    assert data["slWouldHit"] == 1
    assert data["beSavedPct"] == pytest.approx(50.0)
    assert data["byOutcome"]["TP_HIT"]["count"] == 1


async def test_phantom_trades_and_scatter_data_match_response_contract(
    authenticated_client,
    pro_user,
    db_session,
):
    db_session.add_all(
        [
            _phantom_trade(pro_user.id, "tp", "TP_HIT", 2.5),
            _phantom_trade(pro_user.id, "timeout", "TIMEOUT", 0.2),
        ]
    )
    await db_session.commit()

    trades_response = await authenticated_client.get(
        "/api/v1/analytics/phantom/trades?phantom_status=TP_HIT"
    )
    scatter_response = await authenticated_client.get(
        "/api/v1/analytics/phantom/scatter-data?days=30"
    )

    assert trades_response.status_code == 200
    trades = trades_response.json()
    assert trades["total"] == 1
    assert trades["trades"][0]["realTradeId"] == "trade-tp"

    assert scatter_response.status_code == 200
    scatter = scatter_response.json()
    assert scatter["totalPoints"] == 2
    assert {point["tradeId"] for point in scatter["points"]} == {
        "trade-tp",
        "trade-timeout",
    }
