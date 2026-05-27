/**
 * Resolves `mlStateId`, `mlCityId`, and `mlNeighborhoodId` for each zone in zones.json
 * by querying the MercadoLibre public classified_locations API.
 *
 * Hierarchy: state → city → neighborhood
 *   - Mar del Plata: state="Bs.As. Costa Atlántica", city="Mar del Plata", no neighborhood
 *   - Palermo:       state="Capital Federal",        city="Capital Federal", neighborhood="Palermo"
 *
 * - Idempotente: si una zona ya tiene IDs resueltos, no la toca (a menos que pases --force).
 * - Loggea claramente lo que no resuelve y sigue (no aborta).
 * - Matching es case-insensitive + accent-insensitive.
 *
 * Uso:
 *   pnpm --filter @inmobi/shared-types zones:resolve
 *   pnpm --filter @inmobi/shared-types zones:resolve -- --force
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ZONES_PATH = resolve(__dirname, '../src/data/zones.json');

const ML_BASE = 'https://api.mercadolibre.com';

interface MlLocationRef {
  id: string;
  name: string;
}

interface MlCountryDetail {
  id: string;
  name: string;
  states: MlLocationRef[];
}

interface MlStateDetail {
  id: string;
  name: string;
  cities: MlLocationRef[];
}

interface MlCityDetail {
  id: string;
  name: string;
  neighborhoods: MlLocationRef[];
}

interface Zone {
  slug: string;
  displayName: string;
  province: 'Buenos Aires' | 'CABA';
  mlState: string;
  mlCity: string;
  mlNeighborhood?: string;
  mlStateId: string;
  mlCityId: string;
  mlNeighborhoodId?: string;
  aliases: string[];
  priority?: number;
}

interface ZonesFile {
  _comment?: string;
  zones: Zone[];
}

function normalize(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { 'User-Agent': 'inmobi-intel/0.1 (zones-resolver)' } });
  if (!res.ok) throw new Error(`HTTP ${res.status} on ${url}`);
  return (await res.json()) as T;
}

async function loadStateMap(): Promise<Map<string, string>> {
  const country = await fetchJson<MlCountryDetail>(`${ML_BASE}/classified_locations/countries/AR`);
  return new Map(country.states.map((s) => [normalize(s.name), s.id]));
}

async function loadCityMap(stateId: string): Promise<Map<string, string>> {
  const state = await fetchJson<MlStateDetail>(`${ML_BASE}/classified_locations/states/${stateId}`);
  return new Map(state.cities.map((c) => [normalize(c.name), c.id]));
}

async function loadNeighborhoodMap(cityId: string): Promise<Map<string, string>> {
  const city = await fetchJson<MlCityDetail>(`${ML_BASE}/classified_locations/cities/${cityId}`);
  return new Map(city.neighborhoods.map((n) => [normalize(n.name), n.id]));
}

async function main() {
  const force = process.argv.includes('--force');
  const raw = readFileSync(ZONES_PATH, 'utf8');
  const data = JSON.parse(raw) as ZonesFile;

  console.log(`📍 Resolviendo ${data.zones.length} zonas (force=${force})...\n`);

  const stateMap = await loadStateMap();
  const cityMapByState = new Map<string, Map<string, string>>();
  const neighborhoodMapByCity = new Map<string, Map<string, string>>();

  let resolved = 0;
  let skipped = 0;
  const missing: string[] = [];

  for (const zone of data.zones) {
    // Skip if already resolved (unless --force)
    const needsNeighborhood = !!zone.mlNeighborhood;
    const alreadyResolved =
      zone.mlStateId !== '' &&
      zone.mlCityId !== '' &&
      (!needsNeighborhood || !!zone.mlNeighborhoodId);
    if (alreadyResolved && !force) {
      skipped++;
      continue;
    }

    const stateId = stateMap.get(normalize(zone.mlState));
    if (!stateId) {
      missing.push(`${zone.slug}: state "${zone.mlState}" not found`);
      continue;
    }

    if (!cityMapByState.has(stateId)) {
      cityMapByState.set(stateId, await loadCityMap(stateId));
    }
    const cityId = cityMapByState.get(stateId)!.get(normalize(zone.mlCity));
    if (!cityId) {
      missing.push(`${zone.slug}: city "${zone.mlCity}" not found under "${zone.mlState}"`);
      continue;
    }

    let neighborhoodId: string | undefined;
    if (needsNeighborhood) {
      if (!neighborhoodMapByCity.has(cityId)) {
        neighborhoodMapByCity.set(cityId, await loadNeighborhoodMap(cityId));
      }
      neighborhoodId = neighborhoodMapByCity.get(cityId)!.get(normalize(zone.mlNeighborhood!));
      if (!neighborhoodId) {
        missing.push(
          `${zone.slug}: neighborhood "${zone.mlNeighborhood}" not found under "${zone.mlCity}"`,
        );
        continue;
      }
    }

    zone.mlStateId = stateId;
    zone.mlCityId = cityId;
    if (neighborhoodId) zone.mlNeighborhoodId = neighborhoodId;
    resolved++;
    const tail = neighborhoodId ? `/ ${neighborhoodId}` : '';
    console.log(`  ✓ ${zone.slug} → ${stateId} / ${cityId} ${tail}`);
  }

  writeFileSync(ZONES_PATH, JSON.stringify(data, null, 2) + '\n', 'utf8');

  console.log(`\n📊 Resumen:`);
  console.log(`   ✓ Resueltas:  ${resolved}`);
  console.log(`   ↷ Ya estaban: ${skipped}`);
  console.log(`   ✗ Faltantes:  ${missing.length}`);
  if (missing.length > 0) {
    console.log(`\n⚠️  Zonas no resueltas:`);
    for (const m of missing) console.log(`   - ${m}`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('❌ Error:', err);
  process.exit(1);
});
