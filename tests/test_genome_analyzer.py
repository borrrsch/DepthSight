from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from api import models
from api.genome_analyzer import GenomeAnalyzer


pytestmark = pytest.mark.asyncio


def _decision_trace(*foundation_types: str) -> dict:
    return {
        "type": "AND",
        "children": [
            {"type": foundation, "result": True, "children": []}
            for foundation in foundation_types
        ],
    }


async def test_genome_analyzer_discovers_positive_repeated_foundation_combo(
    db_session,
    pro_user,
):
    task = models.Task(
        user_id=pro_user.id,
        task_id="gene-task",
        task_type="backtest",
        status="COMPLETED",
        parameters={},
    )
    run = models.BacktestRun(
        user_id=pro_user.id,
        task=task,
        strategy_name="Gene Strategy",
        symbol="BTCUSDT",
        market_type="futures_usdtm",
        start_date=datetime.now(timezone.utc) - timedelta(days=3),
        end_date=datetime.now(timezone.utc),
        initial_balance=10000,
        parameters_json={},
        status="COMPLETED",
        kpi_results_json={"sharpe_ratio": 1.5, "total_trades": 20},
    )
    run.trades = [
        models.BacktestTrade(
            client_order_id=f"gene-trade-{i}",
            direction="LONG",
            timestamp_entry=datetime.now(timezone.utc) - timedelta(hours=2),
            timestamp_exit=datetime.now(timezone.utc) - timedelta(hours=1),
            entry_price=100.0,
            exit_price=102.0,
            quantity=1.0,
            pnl=10.0,
            commission=0.0,
            exit_reason="TAKE_PROFIT",
            decision_trace_json=_decision_trace("rsi_condition", "trend_direction"),
        )
        for i in range(2)
    ]
    db_session.add(run)
    await db_session.commit()

    unlocked = await GenomeAnalyzer(db_session).analyze_backtest(run)

    assert len(unlocked) == 1
    assert unlocked[0].user_id == pro_user.id
    result = await db_session.execute(
        select(models.Gene).where(models.Gene.id == unlocked[0].gene_id)
    )
    gene = result.scalar_one()
    assert gene.components == ["rsi_condition", "trend_direction"]


async def test_genome_analyzer_does_not_unlock_gene_below_quality_threshold(
    db_session,
    pro_user,
):
    run = models.BacktestRun(
        user_id=pro_user.id,
        task=models.Task(
            user_id=pro_user.id,
            task_id="low-quality-gene-task",
            task_type="backtest",
            status="COMPLETED",
            parameters={},
        ),
        strategy_name="Weak Strategy",
        symbol="BTCUSDT",
        market_type="futures_usdtm",
        start_date=datetime.now(timezone.utc) - timedelta(days=3),
        end_date=datetime.now(timezone.utc),
        initial_balance=10000,
        parameters_json={},
        status="COMPLETED",
        kpi_results_json={"sharpe_ratio": 0.5, "total_trades": 20},
    )
    db_session.add(run)
    await db_session.commit()

    unlocked = await GenomeAnalyzer(db_session).analyze_backtest(run)

    assert unlocked == []
