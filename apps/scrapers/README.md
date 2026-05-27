# apps/scrapers

Workers de scraping en Python 3.11+ con Poetry.

## Estructura

```
apps/scrapers/
├── pyproject.toml
├── scrapers/
│   ├── base.py           # BaseScraper abstracto
│   ├── mercadolibre.py   # MLScraper + CLI entry point
│   ├── parser.py         # Parser HTML puro (sin I/O), testeable
│   ├── models.py         # Modelos Pydantic
│   ├── config.py         # Carga DATABASE_URL + zones.json
│   ├── db.py             # psycopg + upsert helpers
│   ├── exchange.py       # dolarapi.com → blue rate
│   └── logging_config.py # structlog setup
└── tests/
    ├── fixtures/         # HTML capturado de ML real
    └── test_parser.py    # corre sin red
```

## Bootstrap

```bash
# 1. Instalar deps Python
cd apps/scrapers
python -m poetry install

# 2. Bajar Chromium para Playwright
python -m poetry run playwright install chromium

# 3. Crear .env con DATABASE_URL local
cp .env.example .env
```

## Uso

```bash
# Scrapear Mar del Plata (venta + alquiler)
python -m poetry run python -m scrapers.mercadolibre --zone mar-del-plata

# Solo venta, primeras 2 páginas (dev)
python -m poetry run python -m scrapers.mercadolibre --zone mar-del-plata --op SALE --limit 2

# Múltiples zonas
python -m poetry run python -m scrapers.mercadolibre --zone mar-del-plata,palermo,recoleta

# Todas las zonas (corrida full nocturna)
python -m poetry run python -m scrapers.mercadolibre --zone all

# Dry-run: parsea pero no escribe a la DB
python -m poetry run python -m scrapers.mercadolibre --zone palermo --limit 1 --dry-run
```

## Tests

```bash
python -m poetry run pytest                  # todos
python -m poetry run pytest tests/test_parser.py  # solo parser (no red)
```

Los tests del parser leen `tests/fixtures/ml_mdp_venta_real.html` (HTML real capturado). Si ML cambia su HTML y el scraper deja de funcionar, los tests fallan primero — sin necesitar correr el scraper completo. Para refrescar el fixture cuando esto pasa:

```bash
python -m poetry run python scripts/capture_fixture.py   # captura HTML actual a tests/fixtures/
```

## Notas

- **Anti-bot**: ML usa un challenge JS con proof-of-work. Pre-seteamos la cookie `_bm_skipml=true` para bypassearlo en cada sesión (5 min de validez).
- **Performance**: ~5-10s por página, ~5-10 páginas por (zona, op), ~52 zonas × 2 ops = corrida full ~60-90 min.
- **DB writes**: usamos upsert por `(portal, portal_id)`. `last_seen_at` se actualiza siempre; `last_updated_at` solo cuando cambian precio/moneda.
- **USD blue**: al inicio de cada corrida se fetchea de `dolarapi.com/v1/dolares/blue` y se inserta en `usd_rates`. Si falla, se usa el último valor de la DB.
