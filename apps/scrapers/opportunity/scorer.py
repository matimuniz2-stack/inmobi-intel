"""Opportunity scorer — lógica de puntaje pura (sin DB, sin reloj de pared).

Convierte propiedades scrapeadas en oportunidades rankeadas con un score 0-100 y
razones legibles en español. Cuatro señales, según el CLAUDE.md:

  bajo precio    — US$/m² debajo de la mediana de propiedades comparables
  baja reciente  — el precio bajó respecto de una observación anterior
  mucho tiempo   — lleva mucho publicada (proxy: desde que la detectamos)
  urgencia       — el aviso usa lenguaje de urgencia ("dueño vende", "permuta"...)

Principio #4 (explicabilidad): cada punto que suma una propiedad viene con una
razón que un humano le puede leer a su cliente. Nada es caja negra. Todos los
umbrales son constantes arriba del módulo, fáciles de calibrar con uso real.

Se mantiene puro (el reloj `now` se inyecta, sin I/O) para testearlo con fixtures,
igual que los parsers. La cáscara de DB vive en opportunity/__main__.py.

Nota de bootstrap: al arrancar, sólo "bajo precio" y "urgencia" (vía title) tienen
combustible. "baja reciente" se activa cuando el historial acumula cambios, y
"mucho tiempo" cuando los avisos llevan semanas detectados. El scorer ya las
calcula bien; ganan dientes con el tiempo. Ver docs/decisions/005.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

# --- Tunables (documentados; revisar con uso real) ---

# "Bajo precio": US$/m² contra la mediana de la cohorte. La cohorte es por BARRIO
# (no por ciudad): comparar contra toda la ciudad lumpea barrios caros y baratos y
# marca gangas falsas (validado con datos reales — ver decisión 005). Solo APT:
# casas/terrenos tienen US$/m² muy ruidoso porque el lote pesa más que lo construido.
MIN_COHORT = 8  # comparables mínimos (excluyendo la propia) para confiar en la mediana
LOW_PRICE_MIN_DISCOUNT = 0.10  # 10% debajo para disparar
LOW_PRICE_DATA_ERROR_DISCOUNT = 0.30  # >30% debajo: casi siempre dato malo o no comparable
LOW_PRICE_MAX_POINTS = 45
LOW_PRICE_POINTS_PER_DISCOUNT = 150  # 30% de descuento → 45 pts (tope)

# Barrios "catch-all" que no son un barrio real: no sirven para cohortear.
_CATCHALL_NEIGHBORHOODS = {"otros barrios", "otro", "sin especificar"}

# "Baja reciente": comparada sobre US$ normalizado entre observaciones
DROP_WINDOW_DAYS = 90  # la baja tiene que ser reciente para contar
DROP_MIN = 0.03  # 3% de baja para disparar
DROP_MAX_POINTS = 30
DROP_POINTS_PER_DROP = 120  # 25% de baja → 30 pts (tope)

# "Mucho tiempo publicada" (proxy: días desde first_seen_at)
STALE_MIN_DAYS = 60
STALE_MAX_POINTS = 15

# "Urgencia en el texto"
URGENCY_MAX_POINTS = 20

MAX_SCORE = 100
DEFAULT_MIN_SCORE = 15  # debajo de esto no lo mostramos como oportunidad


# --- Tipos ---


@dataclass(frozen=True)
class PropertyRow:
    """Una propiedad activa lista para scorear (subconjunto de columnas)."""

    id: str
    operation_type: str
    property_type: str
    price_amount: Decimal
    price_currency: str
    price_usd: Decimal | None
    covered_sqm: Decimal | None
    total_sqm: Decimal | None
    bedrooms: int | None
    zone_slug: str | None
    neighborhood: str | None
    city: str | None
    title: str | None
    description: str | None
    first_seen_at: datetime


@dataclass(frozen=True)
class PricePoint:
    price_amount: Decimal
    price_currency: str
    price_usd: Decimal | None
    observed_at: datetime


@dataclass(frozen=True)
class Signal:
    key: str  # "low_price" | "price_drop" | "stale" | "urgency"
    points: int
    reason: str  # español, para mostrar
    detail: dict  # estructurado, para la columna signals (auditoría)


@dataclass(frozen=True)
class ScoredOpportunity:
    property_id: str
    score: int
    reasons: list[str] = field(default_factory=list)
    signals: dict = field(default_factory=dict)
    price_usd_at_score: Decimal | None = None


# --- Etiquetas en español ---

_OP_ES = {"SALE": "venta", "RENT": "alquiler", "TEMP_RENT": "alquiler temporal"}
_TYPE_ES_PLURAL = {
    "APT": "departamentos",
    "HOUSE": "casas",
    "PH": "PHs",
    "LOCAL": "locales",
    "TERRENO": "terrenos",
    "OTRO": "propiedades",
}

# (substring normalizado, etiqueta para mostrar, puntos). Fuerte = señal real de
# motivación de venta; débil = marketing genérico que casi todos los avisos ponen.
# Los patrones están sin acentos (el texto se normaliza antes de matchear) y
# elegidos para no solaparse y contar doble (p.ej. "rebaja" ya cubre "rebajado").
_URGENCY_TERMS: list[tuple[str, str, int]] = [
    # fuertes
    ("urgen", "urgente", 12),
    ("dueno vende", "dueño vende", 12),
    ("dueno directo", "dueño directo", 10),
    ("trato directo", "trato directo", 8),
    ("sin comision", "sin comisión", 8),
    ("permuta", "permuta", 10),
    ("remato", "remato", 12),
    ("remate", "remate", 10),
    ("liquido", "liquido", 12),
    ("liquidacion", "liquidación", 10),
    ("escucho oferta", "escucho ofertas", 10),
    ("recibo oferta", "recibo ofertas", 10),
    ("necesito vender", "necesito vender", 12),
    ("vendo ya", "vendo ya", 10),
    ("financ", "financiación", 6),
    # débiles (marketing)
    ("oportunidad", "oportunidad", 4),
    ("imperdible", "imperdible", 4),
    ("rebaja", "rebaja", 6),
    ("excelente precio", "excelente precio", 4),
    ("apto credito", "apto crédito", 4),
    ("ideal inversor", "ideal inversor", 4),
]


# --- Helpers ---


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _fmt_money(x: float) -> str:
    """1150 → '1.150' (separador de miles es-AR)."""
    return f"{int(round(float(x))):,}".replace(",", ".")


def _strip_accents(s: str) -> str:
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _normalize_text(s: str) -> str:
    return _strip_accents(s.lower())


def _join_es(items: list[str]) -> str:
    """['a'] → 'a'; ['a','b'] → 'a y b'; ['a','b','c'] → 'a, b y c'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} y {items[-1]}"


def usd_per_sqm(row: PropertyRow) -> float | None:
    """US$/m² usando superficie cubierta (o total como fallback). None si falta dato."""
    sqm = row.covered_sqm if row.covered_sqm is not None else row.total_sqm
    if row.price_usd is None or sqm is None:
        return None
    sqm_f = float(sqm)
    if sqm_f <= 0:
        return None
    return float(row.price_usd) / sqm_f


def cohort_key(row: PropertyRow) -> tuple[str, str, str, str] | None:
    """Cohorte de comparación: misma operación, tipo y BARRIO (ciudad + neighborhood).

    None si no hay barrio real (sin neighborhood, catch-all, o == ciudad): sin barrio
    no hay comparación justa, así que la propiedad no entra al ranking por precio.
    """
    barrio = (row.neighborhood or "").strip().lower()
    if not barrio or barrio in _CATCHALL_NEIGHBORHOODS:
        return None
    city = (row.city or "").strip().lower()
    if barrio == city:
        return None
    return (row.operation_type, row.property_type, city, barrio)


# --- Estado / antigüedad (Nivel 1: por qué algo está barato) ---
# "Barato por m²" no es lo mismo que "oportunidad": un depto puede estar barato
# porque es viejo / a refaccionar, y entonces está bien de precio para lo que es.
# Inferimos antigüedad y estado del texto del aviso para (a) NO marcar como ganga lo
# que está barato por estado, y (b) poner ese contexto en la razón. Hoy lee el título;
# gana precisión cuando scrapeemos la descripción/detalle (ver decisión 006).

# "A refaccionar" y similares: la baja de precio está explicada por el estado, no es
# ganga para quien busca entrar a vivir. (pattern normalizado sin acentos, display)
_NEEDS_WORK_TERMS: list[tuple[str, str]] = [
    ("a refaccionar", "a refaccionar"),
    ("para refaccionar", "a refaccionar"),
    ("a reciclar", "a reciclar"),
    ("para reciclar", "a reciclar"),
    ("a reformar", "a reformar"),
    ("a demoler", "a demoler"),
    ("apto demolicion", "apto demolición"),
    ("a reparar", "a reparar"),
]


@dataclass(frozen=True)
class Condition:
    antiguedad_years: int | None = None
    a_estrenar: bool = False
    needs_work: bool = False
    terms: list[str] = field(default_factory=list)


def extract_condition(text: str | None) -> Condition:
    """Antigüedad/estado inferidos del texto del aviso (título y/o descripción)."""
    if not text:
        return Condition()
    t = _normalize_text(text)
    a_estrenar = "estrenar" in t  # "a estrenar", "sin estrenar", "nuevo a estrenar"
    years: int | None = 0 if a_estrenar else None
    if years is None:
        # "50 años" → normalizado "50 anos" (la ñ pierde el acento al normalizar)
        m = re.search(r"(\d{1,3})\s*anos\b", t)
        if m and 0 < int(m.group(1)) <= 120:
            years = int(m.group(1))
    terms: list[str] = []
    for pat, disp in _NEEDS_WORK_TERMS:
        if pat in t and disp not in terms:
            terms.append(disp)
    return Condition(
        antiguedad_years=years, a_estrenar=a_estrenar, needs_work=bool(terms), terms=terms
    )


# --- Señales ---


def signal_low_price(row: PropertyRow, peers_usd_per_sqm: list[float]) -> Signal | None:
    """Precio por m² debajo de la mediana del barrio. Solo APT (`peers` excluye la propia)."""
    if row.property_type != "APT":
        return None
    mine = usd_per_sqm(row)
    if mine is None:
        return None
    peers = [v for v in peers_usd_per_sqm if v > 0]
    if len(peers) < MIN_COHORT:
        return None
    median = statistics.median(peers)
    if median <= 0:
        return None
    discount = (median - mine) / median
    # Descuento chico: ruido. Descuento gigante: casi seguro dato malo (cochera
    # mal tipada, terreno como depto, typo de precio). En ambos extremos, no marca.
    if discount < LOW_PRICE_MIN_DISCOUNT or discount > LOW_PRICE_DATA_ERROR_DISCOUNT:
        return None
    # ¿Por qué está barato? Si el aviso dice "a refaccionar/reciclar/demoler", la baja
    # está explicada por el estado: no es ganga para entrar a vivir, no la marcamos.
    cond = extract_condition(" ".join(t for t in (row.title, row.description) if t))
    if cond.needs_work:
        return None
    points = _clamp(round(discount * LOW_PRICE_POINTS_PER_DISCOUNT), 1, LOW_PRICE_MAX_POINTS)
    pct = round(discount * 100)
    reason = (
        f"Precio {pct}% debajo de la mediana del barrio: "
        f"US$ {_fmt_money(mine)}/m² vs US$ {_fmt_money(median)}/m² en "
        f"{len(peers)} {_TYPE_ES_PLURAL.get(row.property_type, 'propiedades')} en "
        f"{_OP_ES.get(row.operation_type, '')} comparables de {row.neighborhood}."
    )
    # Contexto de estado para que el agente juzgue (barato Y nuevo = mejor señal;
    # barato y viejo = parte del descuento puede ser la edad).
    if cond.a_estrenar:
        reason += " A estrenar."
    elif cond.antiguedad_years is not None:
        reason += f" Antigüedad ~{cond.antiguedad_years} años."
    detail = {
        "discount_pct": pct,
        "usd_per_sqm": round(mine, 2),
        "median_usd_per_sqm": round(median, 2),
        "cohort_size": len(peers),
        "antiguedad_years": cond.antiguedad_years,
        "a_estrenar": cond.a_estrenar,
    }
    return Signal("low_price", points, reason, detail)


def signal_price_drop(
    row: PropertyRow, history: list[PricePoint], now: datetime
) -> Signal | None:
    """El precio bajó respecto de una observación anterior, dentro de la ventana."""
    # Comparamos sólo en US$ normalizado: robusto entre fechas y monedas (en ARS,
    # un precio nominal "igual" es una baja real por inflación; el US$ lo captura).
    pts = sorted(
        (p for p in history if p.price_usd is not None), key=lambda p: p.observed_at
    )
    if len(pts) < 2:
        return None
    current = pts[-1]
    curr_usd = float(current.price_usd)  # type: ignore[arg-type]
    # El último precio distinto al actual, yendo hacia atrás.
    prev = next((p for p in reversed(pts[:-1]) if float(p.price_usd) != curr_usd), None)  # type: ignore[arg-type]
    if prev is None:
        return None
    prev_usd = float(prev.price_usd)  # type: ignore[arg-type]
    if prev_usd <= 0:
        return None
    drop = (prev_usd - curr_usd) / prev_usd
    if drop < DROP_MIN:
        return None
    days = (now - current.observed_at).days
    if days > DROP_WINDOW_DAYS:
        return None
    points = _clamp(round(drop * DROP_POINTS_PER_DROP), 1, DROP_MAX_POINTS)
    pct = round(drop * 100)
    when = "hoy" if days <= 0 else ("ayer" if days == 1 else f"hace {days} días")
    reason = (
        f"Bajó de US$ {_fmt_money(prev_usd)} a US$ {_fmt_money(curr_usd)} (-{pct}%) {when}."
    )
    detail = {
        "drop_pct": pct,
        "from_usd": round(prev_usd, 2),
        "to_usd": round(curr_usd, 2),
        "days_ago": days,
    }
    return Signal("price_drop", points, reason, detail)


def signal_stale(row: PropertyRow, now: datetime) -> Signal | None:
    """Lleva mucho tiempo publicada (proxy: días desde que la detectamos)."""
    days = (now - row.first_seen_at).days
    if days < STALE_MIN_DAYS:
        return None
    if days >= 150:
        points = STALE_MAX_POINTS
    elif days >= 90:
        points = 10
    else:
        points = 6
    months = max(2, round(days / 30))
    reason = (
        f"Publicada hace ~{months} meses y sigue activa (posible margen de negociación)."
    )
    return Signal("stale", points, reason, {"days_listed": days})


def signal_urgency(row: PropertyRow) -> Signal | None:
    """El aviso usa lenguaje de urgencia. Lee title + description (hoy sólo title)."""
    parts = [t for t in (row.title, row.description) if t]
    if not parts:
        return None
    text = _normalize_text(" ".join(parts))
    matched: list[tuple[str, int]] = []
    seen: set[str] = set()
    for pattern, display, pts in _URGENCY_TERMS:
        if pattern in text and display not in seen:
            seen.add(display)
            matched.append((display, pts))
    if not matched:
        return None
    matched.sort(key=lambda m: m[1], reverse=True)
    points = _clamp(sum(p for _, p in matched), 1, URGENCY_MAX_POINTS)
    shown = [f"«{d}»" for d, _ in matched[:3]]
    reason = f"El aviso menciona {_join_es(shown)} (señal de urgencia)."
    return Signal("urgency", points, reason, {"terms": [d for d, _ in matched]})


# --- Scoring ---


def score_property(
    row: PropertyRow,
    peers_usd_per_sqm: list[float],
    history: list[PricePoint],
    now: datetime,
) -> ScoredOpportunity | None:
    """Combina las 4 señales. None si ninguna disparó. Score capeado a 100."""
    signals = [
        s
        for s in (
            signal_low_price(row, peers_usd_per_sqm),
            signal_price_drop(row, history, now),
            signal_stale(row, now),
            signal_urgency(row),
        )
        if s is not None
    ]
    if not signals:
        return None
    signals.sort(key=lambda s: s.points, reverse=True)  # razón más fuerte primero
    score = min(MAX_SCORE, sum(s.points for s in signals))
    return ScoredOpportunity(
        property_id=row.id,
        score=score,
        reasons=[s.reason for s in signals],
        signals={s.key: {**s.detail, "points": s.points} for s in signals},
        price_usd_at_score=row.price_usd,
    )


def build_cohorts(
    rows: list[PropertyRow],
) -> dict[tuple[str, str, str, str], list[tuple[str, float]]]:
    """Agrupa US$/m² por cohorte (op, tipo, ciudad, barrio). key → [(property_id, ups)]."""
    cohorts: dict[tuple[str, str, str, str], list[tuple[str, float]]] = {}
    for row in rows:
        key = cohort_key(row)
        v = usd_per_sqm(row)
        if key is None or v is None or v <= 0:
            continue
        cohorts.setdefault(key, []).append((row.id, v))
    return cohorts


def score_all(
    rows: list[PropertyRow],
    histories: dict[str, list[PricePoint]],
    now: datetime,
    *,
    min_score: int = DEFAULT_MIN_SCORE,
) -> list[ScoredOpportunity]:
    """Scorea todas las filas y devuelve las que llegan a `min_score`, ordenadas desc."""
    cohorts = build_cohorts(rows)
    out: list[ScoredOpportunity] = []
    for row in rows:
        key = cohort_key(row)
        peers = (
            [v for (cid, v) in cohorts.get(key, []) if cid != row.id]
            if key is not None
            else []
        )
        scored = score_property(row, peers, histories.get(row.id, []), now)
        if scored is not None and scored.score >= min_score:
            out.append(scored)
    out.sort(key=lambda s: s.score, reverse=True)
    return out
