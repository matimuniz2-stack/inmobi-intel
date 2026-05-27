import zonesData from './data/zones.json' with { type: 'json' };

export type Province = 'Buenos Aires' | 'CABA';

export interface Zone {
  /** url-safe identifier, used in DB column `zone_slug` and CLI args */
  slug: string;
  /** human-readable label for autocomplete */
  displayName: string;
  province: Province;

  // === Canonical ML location names — used by the resolver ===
  /** Exact ML state name (e.g., "Bs.As. Costa Atlántica", "Capital Federal") */
  mlState: string;
  /** Exact ML city name (e.g., "Mar del Plata", "Capital Federal") */
  mlCity: string;
  /** Exact ML neighborhood name (only set when zone operates at neighborhood level) */
  mlNeighborhood?: string;

  // === Resolved IDs — written by `pnpm zones:resolve` ===
  mlStateId: string;
  mlCityId: string;
  mlNeighborhoodId?: string;

  /** Lowercase search terms (no accents) for autocomplete matching. */
  aliases: string[];
  /** Higher = shown earlier in autocomplete suggestions (default 0). */
  priority?: number;
}

interface ZonesFile {
  zones: Zone[];
}

const file = zonesData as ZonesFile;

export const zones: readonly Zone[] = file.zones;

export const zonesBySlug: ReadonlyMap<string, Zone> = new Map(zones.map((z) => [z.slug, z]));

function normalize(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .trim();
}

/**
 * Returns zones matching a free-text query against displayName / slug / aliases.
 * Case- and accent-insensitive. Sorted by priority (desc) then displayName.
 */
export function findZonesByQuery(query: string, limit = 10): Zone[] {
  const q = normalize(query);
  if (!q) return [];

  const matches = zones.filter((z) => {
    if (normalize(z.slug).includes(q)) return true;
    if (normalize(z.displayName).includes(q)) return true;
    return z.aliases.some((a) => normalize(a).includes(q));
  });

  return [...matches]
    .sort((a, b) => {
      const pa = a.priority ?? 0;
      const pb = b.priority ?? 0;
      if (pa !== pb) return pb - pa;
      return a.displayName.localeCompare(b.displayName, 'es');
    })
    .slice(0, limit);
}
