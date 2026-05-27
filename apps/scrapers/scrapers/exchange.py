"""Fetches the blue USD rate from dolarapi.com."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import UsdRateRecord

DOLAR_BLUE_URL = "https://dolarapi.com/v1/dolares/blue"
SOURCE = "dolarapi.com/blue"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
async def fetch_blue_rate() -> UsdRateRecord:
    """Returns the latest blue rate as a UsdRateRecord. Raises on persistent failure."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(DOLAR_BLUE_URL)
        resp.raise_for_status()
        data = resp.json()
    # dolarapi returns {"compra": <buy>, "venta": <sell>, "moneda": "USD", "casa": "blue", ...}
    # We use the sell (venta) rate — more conservative for property valuation in USD.
    rate = Decimal(str(data["venta"]))
    return UsdRateRecord(source=SOURCE, rate=rate, fetched_at=datetime.now(timezone.utc))
