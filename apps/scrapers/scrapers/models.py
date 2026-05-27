"""Pydantic models that mirror the Prisma schema columns."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

Operation = Literal["SALE", "RENT", "TEMP_RENT"]
PropertyType = Literal["APT", "HOUSE", "PH", "LOCAL", "TERRENO", "OTRO"]
Currency = Literal["ARS", "USD"]
Portal = Literal["MERCADOLIBRE"]


class MlListingCard(BaseModel):
    """A single listing card parsed from a MercadoLibre search results page."""

    model_config = ConfigDict(extra="forbid")

    portal_id: str
    url: str
    title: str
    operation_type: Operation
    property_type: PropertyType
    price_amount: Decimal
    price_currency: Currency
    address_full: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    province: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    total_sqm: Decimal | None = None
    covered_sqm: Decimal | None = None
    photos: list[str] = []
    agency_name: str | None = None


class UsdRateRecord(BaseModel):
    source: str
    rate: Decimal
    fetched_at: datetime
