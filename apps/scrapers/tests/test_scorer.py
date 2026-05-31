"""Tests del scorer de oportunidades. Lógica pura, sin DB ni reloj real."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from opportunity.scorer import (
    MAX_SCORE,
    PricePoint,
    PropertyRow,
    build_cohorts,
    score_all,
    score_property,
    signal_low_price,
    signal_price_drop,
    signal_stale,
    signal_urgency,
    usd_per_sqm,
)

NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


def make_row(**kw) -> PropertyRow:
    base = {
        "id": "p1",
        "operation_type": "SALE",
        "property_type": "APT",
        "price_amount": Decimal("100000"),
        "price_currency": "USD",
        "price_usd": Decimal("100000"),
        "covered_sqm": Decimal("50"),
        "total_sqm": Decimal("55"),
        "bedrooms": 2,
        "zone_slug": "playa-grande",
        "city": "Mar del Plata",
        "title": None,
        "description": None,
        "first_seen_at": NOW,
    }
    base.update(kw)
    return PropertyRow(**base)


def point(days_ago: int, usd: str | None, amount: str = "100000", cur: str = "USD") -> PricePoint:
    return PricePoint(
        price_amount=Decimal(amount),
        price_currency=cur,
        price_usd=Decimal(usd) if usd is not None else None,
        observed_at=NOW - timedelta(days=days_ago),
    )


# --- usd_per_sqm ---


def test_usd_per_sqm_uses_covered_then_total():
    assert usd_per_sqm(make_row(covered_sqm=Decimal("50"))) == 2000.0
    assert usd_per_sqm(make_row(covered_sqm=None, total_sqm=Decimal("80"))) == 1250.0


def test_usd_per_sqm_none_when_missing():
    assert usd_per_sqm(make_row(price_usd=None)) is None
    assert usd_per_sqm(make_row(covered_sqm=None, total_sqm=None)) is None
    assert usd_per_sqm(make_row(covered_sqm=Decimal("0"), total_sqm=None)) is None


# --- bajo precio ---


def test_low_price_fires_with_discount():
    row = make_row(price_usd=Decimal("100000"), covered_sqm=Decimal("50"))  # 2000/m²
    peers = [2500.0] * 6  # mediana 2500 → 20% debajo
    sig = signal_low_price(row, peers)
    assert sig is not None
    assert sig.key == "low_price"
    assert sig.points == 30  # round(0.20 * 150)
    assert "20% debajo" in sig.reason
    assert "Playa Grande" in sig.reason


def test_low_price_ignores_small_discount():
    row = make_row(price_usd=Decimal("100000"), covered_sqm=Decimal("50"))  # 2000/m²
    assert signal_low_price(row, [2100.0] * 6) is None  # ~4.8% debajo, ruido


def test_low_price_ignores_data_error_discount():
    row = make_row(price_usd=Decimal("100000"), covered_sqm=Decimal("50"))  # 2000/m²
    # mediana 6000 → 67% debajo: dato malo, no se marca
    assert signal_low_price(row, [6000.0] * 6) is None


def test_low_price_needs_minimum_cohort():
    row = make_row(price_usd=Decimal("100000"), covered_sqm=Decimal("50"))
    assert signal_low_price(row, [2500.0] * 5) is None  # < MIN_COHORT


def test_low_price_caps_points():
    row = make_row(price_usd=Decimal("100000"), covered_sqm=Decimal("50"))  # 2000/m²
    sig = signal_low_price(row, [4000.0] * 6)  # 50% debajo
    assert sig is not None and sig.points == 45  # tope


# --- baja reciente ---


def test_price_drop_fires_within_window():
    row = make_row()
    hist = [point(10, "120000"), point(3, "100000")]
    sig = signal_price_drop(row, hist, NOW)
    assert sig is not None
    assert sig.points == 20  # round(0.1667 * 120)
    assert "hace 3 días" in sig.reason
    assert "120.000" in sig.reason and "100.000" in sig.reason


def test_price_drop_ignored_outside_window():
    row = make_row()
    hist = [point(200, "120000"), point(100, "100000")]  # baja hace 100d (>90)
    assert signal_price_drop(row, hist, NOW) is None


def test_price_drop_ignores_increase():
    row = make_row()
    hist = [point(10, "100000"), point(3, "120000")]  # subió
    assert signal_price_drop(row, hist, NOW) is None


def test_price_drop_needs_two_usd_points():
    row = make_row()
    assert signal_price_drop(row, [point(3, "100000")], NOW) is None
    # dos puntos pero mismo precio → no hay baja
    assert signal_price_drop(row, [point(10, "100000"), point(3, "100000")], NOW) is None


# --- mucho tiempo publicada ---


def test_stale_fires_past_threshold():
    sig = signal_stale(make_row(first_seen_at=NOW - timedelta(days=80)), NOW)
    assert sig is not None and sig.points == 6
    sig2 = signal_stale(make_row(first_seen_at=NOW - timedelta(days=200)), NOW)
    assert sig2 is not None and sig2.points == 15  # tope


def test_stale_silent_when_fresh():
    assert signal_stale(make_row(first_seen_at=NOW - timedelta(days=30)), NOW) is None


# --- urgencia ---


def test_urgency_strong_terms_cap_at_20():
    sig = signal_urgency(make_row(title="DUEÑO VENDE, URGENTE - escucho ofertas"))
    assert sig is not None
    assert sig.points == 20  # 12+12+10 capeado a 20
    assert "«urgente»" in sig.reason or "«dueño vende»" in sig.reason


def test_urgency_weak_term_low_points():
    sig = signal_urgency(make_row(title="Excelente oportunidad de inversión"))
    assert sig is not None and sig.points == 4  # sólo "oportunidad"


def test_urgency_handles_accents_and_reads_description():
    sig = signal_urgency(make_row(title=None, description="Vendo por permuta, trato directo"))
    assert sig is not None
    assert "permuta" in sig.detail["terms"]
    assert "trato directo" in sig.detail["terms"]


def test_urgency_none_without_text():
    assert signal_urgency(make_row(title=None, description=None)) is None


# --- scoring combinado ---


def test_score_property_combines_and_caps():
    row = make_row(
        title="DUEÑO VENDE URGENTE permuta liquido",  # urgencia tope 20
        first_seen_at=NOW - timedelta(days=200),  # stale 15
    )
    hist = [point(10, "150000"), point(2, "100000")]  # baja 33% → tope 30
    peers = [4000.0] * 6  # bajo precio 50% → tope 45
    scored = score_property(row, peers, hist, NOW)
    assert scored is not None
    assert scored.score == MAX_SCORE  # 45+30+15+20 = 110 → capeado a 100
    assert len(scored.reasons) == 4
    assert set(scored.signals) == {"low_price", "price_drop", "stale", "urgency"}
    # razón más fuerte primero (low_price = 45 pts, el tope individual)
    assert scored.reasons[0].startswith("Precio ")


def test_score_property_none_without_signals():
    assert score_property(make_row(), [], [], NOW) is None


def test_score_all_filters_min_score_and_sorts():
    # Cohorte de 6 deptos a 2500/m² + 1 candidato barato a 2000/m²
    peers = [
        make_row(id=f"peer{i}", price_usd=Decimal("125000"), covered_sqm=Decimal("50"))
        for i in range(6)
    ]
    candidate = make_row(id="cand", price_usd=Decimal("100000"), covered_sqm=Decimal("50"))
    # Un depto con sólo marketing débil ("oportunidad", 4 pts) no llega al mínimo
    weak = make_row(
        id="weak", price_usd=Decimal("125000"), covered_sqm=Decimal("50"),
        title="Gran oportunidad", zone_slug="otra-zona",
    )
    rows = [*peers, candidate, weak]
    result = score_all(rows, histories={}, now=NOW)
    ids = [s.property_id for s in result]
    assert "cand" in ids
    assert "weak" not in ids  # 4 pts < min_score
    # ordenado desc
    assert all(result[i].score >= result[i + 1].score for i in range(len(result) - 1))


def test_build_cohorts_groups_by_op_type_zone():
    rows = [
        make_row(id="a", zone_slug="z1"),
        make_row(id="b", zone_slug="z1"),
        make_row(id="c", zone_slug="z2"),
        make_row(id="d", operation_type="RENT", zone_slug="z1"),
    ]
    cohorts = build_cohorts(rows)
    assert len(cohorts[("SALE", "APT", "z1")]) == 2
    assert len(cohorts[("SALE", "APT", "z2")]) == 1
    assert len(cohorts[("RENT", "APT", "z1")]) == 1
