"""Apply discovered Argenprop/ZonaProp barrio slugs to zones.json (T1).

The mapping below was built by hand from scripts/out/slug-candidates.json
(facet links harvested live from each portal by discover_barrio_slugs.py) —
every slug here was seen verbatim on the portal, none are guesses.

Two kinds of changes:
1. Existing MdP barrio zones get argenpropSlug / zonapropSlug.
2. Barrios that both portals list but zones.json lacked are appended as new
   zones. They get mlNeighborhood (so ML *can* target them once validated)
   but NO mlNeighborhoodId — the orchestrator only sends ML zones whose
   neighborhood was resolved against ML (`pnpm zones:resolve`), so unresolved
   ones are skipped there instead of risking a silent city-wide fallback.

Idempotent: re-running rewrites the same values.
"""

from __future__ import annotations

import json
from pathlib import Path

ZONES_FILE = (
    Path(__file__).resolve().parents[3]
    / "packages" / "shared-types" / "src" / "data" / "zones.json"
)

# zone slug -> (argenpropSlug, zonapropSlug); None = portal doesn't expose it
EXISTING: dict[str, tuple[str | None, str | None]] = {
    "centro": ("centro-mdp", "centro-mar-del-plata"),
    "la-perla": (None, "la-perla"),  # Argenprop splits it: see la-perla-norte/sur below
    "playa-grande": ("playa-grande-mdp", "playa-grande-mar-del-plata"),
    "playa-chica": ("playa-chica", "playa-chica"),
    "stella-maris": ("stella-maris", "stella-maris"),
    "los-troncos": ("los-troncos-mdp", "los-troncos-mar-del-plata"),
    "chauvin": ("chauvin", "chauvin"),
    "guemes": ("zona-guemes", "guemes-mar-del-plata"),
    "san-carlos": ("san-carlos-mdp", "san-carlos-mar-del-plata"),
    "punta-mogotes": ("punta-mogotes", "punta-mogotes"),
    "pinares": ("los-pinares", "los-pinares"),
    "caisamar": ("caisamar", "caisamar"),
    "constitucion-mdp": ("constitucion-mdp", "constitucion-mar-del-plata"),
    "bosques-peralta-ramos": ("br-bosque-peralta-ramos", "bosque-peralta-ramos"),
    "el-faro": ("faro-mdp", None),
    "las-avenidas": ("las-avenidas", "las-avenidas"),
    "los-acantilados": ("los-acantilados", "los-acantilados"),
    "macrocentro": ("macrocentro-mdp", "macrocentro"),
    "nueva-pompeya-mdp": ("pompeya-mdp", "nueva-pompeya-mar-del-plata"),
    "parque-camet": ("camet-mdp", "barrio-camet"),
    "parque-luro": ("parque-luro-mdp", "parque-luro"),
    "plaza-colon": ("plaza-colon", None),
    "plaza-mitre": ("plaza-mitre", None),
    "puerto-mdp": ("puerto", "puerto"),
    "rumenco": ("rumenco", "rumenco"),
    "san-jose": ("san-jose-mdp", "san-jose-mar-del-plata"),
    "terminal-vieja": ("terminal-vieja", "terminal-vieja"),
    "torreon": ("torreon", "torreon"),
    "varese": ("varese", "playa-varese"),
    # No facet found on either portal (stay ML-only):
    # barrio-bosque-grande, bristol, las-lilas, los-robles, terminal-nueva,
    # tierras-del-mar, tribunales, zacagnini
}

# (slug, displayName, mlNeighborhood, argenpropSlug, zonapropSlug, aliases)
NEW_ZONES: list[tuple[str, str, str, str | None, str | None, list[str]]] = [
    ("villa-primera", "Villa Primera", "Villa Primera",
     "villa-primera", "villa-primera", []),
    ("san-juan-mdp", "San Juan (MdP)", "San Juan",
     "san-juan-mdp", "san-juan-mar-del-plata", []),
    ("alem", "Alem", "Alem", None, "alem", []),
    ("punta-iglesia", "Punta Iglesia", "Punta Iglesia", None, "punta-iglesia", []),
    ("alfar", "Alfar", "Alfar", None, "alfar", []),
    ("sierra-de-los-padres", "Sierra de los Padres", "Sierra de los Padres",
     "sierra-de-los-padres-mdp", "sierra-de-los-padres", ["sierra"]),
    ("don-bosco-mdp", "Don Bosco (MdP)", "Don Bosco",
     "don-bosco-mdp", "don-bosco-mar-del-plata", []),
    ("bernardino-rivadavia", "Bernardino Rivadavia", "Bernardino Rivadavia",
     "bernardino-rivadavia-mdp", "bernardino-rivadavia", []),
    ("el-gaucho", "El Gaucho", "El Gaucho", "el-gaucho-mdp", None, []),
    ("arenas-del-sur", "Arenas del Sur", "Arenas del Sur",
     "arenas-del-sur", "arenas-del-sur", []),
    ("la-perla-norte", "La Perla Norte", "La Perla Norte",
     "la-perla-norte", "barrio-la-perla-norte", []),
    ("la-perla-sur", "La Perla Sur", "La Perla Sur", "la-perla-sur", None, []),
    ("santa-monica", "Santa Mónica", "Santa Mónica", None, "santa-monica", []),
    ("playa-serena", "Playa Serena", "Playa Serena", None, "playa-serena", []),
    ("faro-norte", "Faro Norte", "Faro Norte", None, "faro-norte", []),
    ("colinas-de-peralta-ramos", "Colinas de Peralta Ramos", "Colinas de Peralta Ramos",
     "br-colinas-de-peralta-ramos", "colina-de-peralta-ramos", []),
    ("lopez-de-gomara", "López de Gomara", "López de Gomara", "lopez-de-gomara", None, []),
    ("el-marquesado", "El Marquesado", "El Marquesado", "el-marquesado-mdp",
     "el-marquesado-mar-del-plata", []),
    ("pinos-de-anchorena", "Pinos de Anchorena", "Pinos de Anchorena",
     None, "pinos-de-anchorena", []),
]

MDP_STATE_ID = "TUxBUENPU2ExMmFkMw"
MDP_CITY_ID = "TUxBQ01BUjU2MGMw"


def main() -> None:
    data = json.loads(ZONES_FILE.read_text(encoding="utf-8"))
    by_slug = {z["slug"]: z for z in data["zones"]}

    changed = 0
    for slug, (ap, zp) in EXISTING.items():
        zone = by_slug.get(slug)
        if zone is None:
            print(f"WARN: zone {slug!r} not found in zones.json")
            continue
        if ap:
            zone["argenpropSlug"] = ap
        if zp:
            zone["zonapropSlug"] = zp
        changed += 1

    added = 0
    for slug, name, ml_barrio, ap, zp, aliases in NEW_ZONES:
        if slug in by_slug:
            zone = by_slug[slug]
        else:
            zone = {
                "slug": slug,
                "displayName": name,
                "province": "Buenos Aires",
                "mlState": "Bs.As. Costa Atlántica",
                "mlCity": "Mar del Plata",
                "mlNeighborhood": ml_barrio,
                "mlStateId": MDP_STATE_ID,
                "mlCityId": MDP_CITY_ID,
                "aliases": aliases,
                "priority": 85,
            }
            data["zones"].append(zone)
            by_slug[slug] = zone
            added += 1
        if ap:
            zone["argenpropSlug"] = ap
        if zp:
            zone["zonapropSlug"] = zp

    # newline="\n": the file is LF in the repo; CRLF would rewrite every line.
    with ZONES_FILE.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"updated {changed} existing zones, added {added} new zones -> {ZONES_FILE}")


if __name__ == "__main__":
    main()
