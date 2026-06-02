"""Tests del scorer de oportunidades. Lógica pura, sin DB ni reloj real."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from opportunity.scorer import (
    MAX_SCORE,
    PricePoint,
    PropertyRow,
    build_cohorts,
    cohort_key,
    extract_condition,
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
        "neighborhood": "Centro",
        "city": "Mar del Plata",
        "title": None,
        "description": None,
        "first_seen_at": NOW,
    }
    base.update(kw)
    return PropertyRow(**base)


def point(
    days_ago: int, usd: str | None, amount: str | None = None, cur: str = "USD"
) -> PricePoint:
    # En un aviso en USD el monto nominal == el US$ normalizado; por defecto los
    # alineamos para que los fixtures reflejen la realidad (la baja se mide en nominal).
    if amount is None:
        amount = usd if usd is not None else "0"
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
    peers = [2500.0] * 8  # mediana 2500 → 20% debajo
    sig = signal_low_price(row, peers)
    assert sig is not None
    assert sig.key == "low_price"
    assert sig.points == 30  # round(0.20 * 150)
    assert "20% debajo" in sig.reason
    assert "del barrio" in sig.reason
    assert "Centro" in sig.reason  # nombre del barrio


def test_low_price_ignores_small_discount():
    row = make_row(price_usd=Decimal("100000"), covered_sqm=Decimal("50"))  # 2000/m²
    assert signal_low_price(row, [2100.0] * 8) is None  # ~4.8% debajo, ruido


def test_low_price_ignores_data_error_discount():
    row = make_row(price_usd=Decimal("100000"), covered_sqm=Decimal("50"))  # 2000/m²
    # mediana 3200 → 37% debajo: dato malo / no comparable (>30%), no se marca
    assert signal_low_price(row, [3200.0] * 8) is None


def test_low_price_needs_minimum_cohort():
    row = make_row(price_usd=Decimal("100000"), covered_sqm=Decimal("50"))
    assert signal_low_price(row, [2500.0] * 7) is None  # < MIN_COHORT (8)


def test_low_price_caps_points():
    row = make_row(price_usd=Decimal("100000"), covered_sqm=Decimal("50"))  # 2000/m²
    sig = signal_low_price(row, [2857.0] * 8)  # ~30% debajo (tope de la banda)
    assert sig is not None and sig.points == 45  # tope


def test_low_price_only_apt():
    # Casas/terrenos no entran a "bajo precio" (US$/m² muy ruidoso por el lote)
    row = make_row(property_type="HOUSE", price_usd=Decimal("100000"), covered_sqm=Decimal("50"))
    assert signal_low_price(row, [2500.0] * 8) is None


def test_cohort_key_requires_real_neighborhood():
    assert cohort_key(make_row(neighborhood="Centro")) == ("SALE", "APT", "mar del plata", "centro")
    assert cohort_key(make_row(neighborhood=None)) is None
    assert cohort_key(make_row(neighborhood="Otros Barrios")) is None  # catch-all
    assert cohort_key(make_row(neighborhood="Mar del Plata")) is None  # == ciudad


# --- estado / antigüedad (Nivel 1) ---


def test_extract_condition():
    c = extract_condition("Depto 2 amb 50 años, 48m2")
    assert c.antiguedad_years == 50 and not c.a_estrenar and not c.needs_work
    c2 = extract_condition("Hermoso a estrenar con cochera")
    assert c2.a_estrenar and c2.antiguedad_years == 0
    c3 = extract_condition("Oportunidad, a refaccionar")
    assert c3.needs_work and "a refaccionar" in c3.terms
    c0 = extract_condition(None)
    assert c0.antiguedad_years is None and not c0.a_estrenar and not c0.needs_work


def test_extract_condition_ignores_warranty_years():
    # "3 años de garantía" / "10 años de financiación" NO son antigüedad
    assert extract_condition("Cocina nueva, 3 años de garantía").antiguedad_years is None
    assert extract_condition("10 años de financiación directa").antiguedad_years is None
    # pero "antigüedad 30 años" sí
    assert extract_condition("Antigüedad 30 años, muy cuidado").antiguedad_years == 30


def test_low_price_needs_work_gets_haircut_not_suppressed():
    # Barato y "a refaccionar": sigue siendo negocio (inversor/flip) pero con menos
    # puntos y la razón lo aclara. Decisión 006 / opción A del megaplan.
    row = make_row(
        price_usd=Decimal("100000"), covered_sqm=Decimal("50"),
        title="Depto 2 amb a refaccionar",
    )
    sig = signal_low_price(row, [2500.0] * 8)  # 20% debajo
    assert sig is not None
    assert sig.points == 15  # round(30 * 0.5) — mitad del puntaje pleno
    assert "a refaccionar" in sig.reason and "estado" in sig.reason
    assert sig.detail["needs_work"] is True


def test_low_price_requires_covered_sqm():
    # Sin superficie cubierta no entra al cálculo de bajo precio (US$/m² no homogéneo)
    row = make_row(price_usd=Decimal("100000"), covered_sqm=None, total_sqm=Decimal("80"))
    assert signal_low_price(row, [2500.0] * 8) is None


def test_low_price_adds_condition_context():
    row = make_row(
        price_usd=Decimal("100000"), covered_sqm=Decimal("50"), title="Depto a estrenar",
    )
    sig = signal_low_price(row, [2500.0] * 8)
    assert sig is not None and "A estrenar." in sig.reason and sig.detail["a_estrenar"]
    row2 = make_row(
        price_usd=Decimal("100000"), covered_sqm=Decimal("50"), title="Depto 50 años",
    )
    sig2 = signal_low_price(row2, [2500.0] * 8)
    assert sig2 is not None and "Antigüedad ~50 años." in sig2.reason


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


def test_price_drop_ignores_ars_dollar_artifact():
    # Aviso en ARS, monto nominal IGUAL, pero el dólar subió → el US$ "bajó".
    # No es una baja real (el dueño no tocó el precio): no debe marcar.
    row = make_row()
    hist = [
        point(10, "50000", amount="50000000", cur="ARS"),  # 50M ARS ≈ US$50k
        point(2, "45000", amount="50000000", cur="ARS"),   # mismo nominal, US$ bajó
    ]
    assert signal_price_drop(row, hist, NOW) is None


def test_price_drop_real_ars_nominal_drop_fires():
    row = make_row()
    hist = [
        point(10, "60000", amount="60000000", cur="ARS"),
        point(2, "50000", amount="50000000", cur="ARS"),  # bajó 10M nominal
    ]
    sig = signal_price_drop(row, hist, NOW)
    assert sig is not None
    assert sig.reason.startswith("Bajó de $")  # moneda del aviso (ARS), no US$
    assert sig.detail["currency"] == "ARS" and not sig.detail["cross_currency"]


def test_price_drop_cross_currency_falls_back_to_usd():
    # El aviso cambió de ARS a USD entre observaciones → comparar en US$, aclarándolo.
    row = make_row()
    hist = [
        point(10, "50000", amount="50000000", cur="ARS"),
        point(2, "45000", amount="45000", cur="USD"),
    ]
    sig = signal_price_drop(row, hist, NOW)
    assert sig is not None
    assert "estimado en US$" in sig.reason
    assert sig.detail["cross_currency"] is True


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


def test_urgency_detects_sucesion():
    # El ejemplo canónico del plan ("sucesión urgente") antes no detectaba "sucesión"
    sig = signal_urgency(make_row(title="Sucesión, escucho ofertas"))
    assert sig is not None
    assert "sucesión" in sig.detail["terms"]


def test_urgency_none_without_text():
    assert signal_urgency(make_row(title=None, description=None)) is None


# --- scoring combinado ---


def test_score_property_combines_and_caps():
    row = make_row(
        title="DUEÑO VENDE URGENTE permuta liquido",  # urgencia tope 20
        first_seen_at=NOW - timedelta(days=200),  # stale 15
    )
    hist = [point(10, "150000"), point(2, "100000")]  # baja 33% → tope 30
    peers = [2857.0] * 8  # bajo precio ~30% → tope 45
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
    # Cohorte (Centro) de 8 deptos a 2500/m² + 1 candidato barato a 2000/m²
    peers = [
        make_row(id=f"peer{i}", price_usd=Decimal("125000"), covered_sqm=Decimal("50"))
        for i in range(8)
    ]
    candidate = make_row(id="cand", price_usd=Decimal("100000"), covered_sqm=Decimal("50"))
    # Un depto en otro barrio (sin cohorte) con sólo marketing débil no llega al mínimo
    weak = make_row(
        id="weak", price_usd=Decimal("125000"), covered_sqm=Decimal("50"),
        title="Gran oportunidad", neighborhood="Sin Comparables",
    )
    rows = [*peers, candidate, weak]
    result = score_all(rows, histories={}, now=NOW)
    ids = [s.property_id for s in result]
    assert "cand" in ids
    assert "weak" not in ids  # 4 pts < min_score
    # ordenado desc
    assert all(result[i].score >= result[i + 1].score for i in range(len(result) - 1))


def test_build_cohorts_groups_by_op_type_neighborhood():
    rows = [
        make_row(id="a", neighborhood="Centro"),
        make_row(id="b", neighborhood="Centro"),
        make_row(id="c", neighborhood="Güemes"),
        make_row(id="d", operation_type="RENT", neighborhood="Centro"),
    ]
    cohorts = build_cohorts(rows)
    assert len(cohorts[("SALE", "APT", "mar del plata", "centro")]) == 2
    assert len(cohorts[("SALE", "APT", "mar del plata", "güemes")]) == 1
    assert len(cohorts[("RENT", "APT", "mar del plata", "centro")]) == 1
