"""Config loading: DATABASE_URL, zones.json path."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# apps/scrapers/scrapers/config.py → ../../../  is project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRAPERS_ROOT = Path(__file__).resolve().parents[1]

# Load .env from local first, then project root
for env_path in (SCRAPERS_ROOT / ".env", PROJECT_ROOT / ".env"):
    if env_path.exists():
        load_dotenv(env_path)
        break

DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

ZONES_FILE: Path = PROJECT_ROOT / "packages" / "shared-types" / "src" / "data" / "zones.json"


def load_zones() -> list[dict[str, Any]]:
    with ZONES_FILE.open(encoding="utf-8") as f:
        data = json.load(f)
    return data["zones"]


def get_zone(slug: str) -> dict[str, Any]:
    for z in load_zones():
        if z["slug"] == slug:
            return z
    raise KeyError(f"Zone not found: {slug}")
