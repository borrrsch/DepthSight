from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from api.og_image_generator import _generate_equity_svg_path, generate_og_image
from api.schemas import SharedBacktestData, SharedBacktestPeriod


def _shared_data(equity_curve):
    return SharedBacktestData(
        strategyName="Shared Strategy",
        symbol="BTCUSDT",
        period=SharedBacktestPeriod(
            start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end=datetime(2024, 1, 2, tzinfo=timezone.utc),
        ),
        kpis={"total_return_pct": 12.5, "max_drawdown_pct": 3.0},
        equityCurve=equity_curve,
        parameters={},
    )


def test_generate_equity_svg_path_handles_empty_and_flat_curves():
    assert _generate_equity_svg_path([], width=400, height=160) == ""

    path = _generate_equity_svg_path([[0, 1000], [1, 1000]], width=400, height=160)

    assert path.startswith("M ")
    assert "L" in path


async def test_generate_og_image_returns_png_bytes_for_shared_backtest():
    class FakeBrowser:
        async def new_page(self):
            page = AsyncMock()
            page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\nfake-image")
            return page

        async def close(self):
            return None

    class FakePlaywright:
        chromium = AsyncMock()

        async def __aenter__(self):
            self.chromium.launch = AsyncMock(return_value=FakeBrowser())
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with patch(
        "api.og_image_generator.async_playwright", return_value=FakePlaywright()
    ):
        image = await generate_og_image(_shared_data([[0, 1000], [1, 1125]]))

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert image == b"\x89PNG\r\n\x1a\nfake-image"
