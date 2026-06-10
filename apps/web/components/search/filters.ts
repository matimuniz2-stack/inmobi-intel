/** Tipos y helpers de filtros compartidos entre /buscar, /mapa y /oportunidades. */

export type Operation = 'SALE' | 'RENT' | 'TEMP_RENT' | '';
export type PropertyType = 'APT' | 'HOUSE' | 'PH' | 'LOCAL' | 'TERRENO' | 'OTRO' | '';
export type Sort = 'recent' | 'price_asc' | 'price_desc';
export type BedroomsFilter = '' | '1' | '2' | '3' | '4' | '5plus';
export type BathroomsFilter = '' | '1' | '2' | '3';

/** Debe coincidir con FEATURE_KEYWORDS del server (property-filters.ts). */
export type FeatureKey =
  | 'cochera'
  | 'quincho'
  | 'pileta'
  | 'parrilla'
  | 'balcon'
  | 'terraza'
  | 'patio'
  | 'jardin'
  | 'vista_al_mar'
  | 'a_estrenar'
  | 'apto_credito'
  | 'amoblado';

export const FEATURE_OPTIONS: { key: FeatureKey; label: string }[] = [
  { key: 'cochera', label: 'Cochera' },
  { key: 'quincho', label: 'Quincho' },
  { key: 'pileta', label: 'Pileta' },
  { key: 'parrilla', label: 'Parrilla' },
  { key: 'balcon', label: 'Balcón' },
  { key: 'terraza', label: 'Terraza' },
  { key: 'patio', label: 'Patio' },
  { key: 'jardin', label: 'Jardín' },
  { key: 'vista_al_mar', label: 'Vista al mar' },
  { key: 'a_estrenar', label: 'A estrenar' },
  { key: 'apto_credito', label: 'Apto crédito' },
  { key: 'amoblado', label: 'Amoblado' },
];

export interface Filters {
  zoneSlug: string | null;
  operationType: Operation;
  propertyType: PropertyType;
  bedrooms: BedroomsFilter;
  bathrooms: BathroomsFilter;
  priceUsdMin: string;
  priceUsdMax: string;
  sqmMin: string;
  sqmMax: string;
  features: FeatureKey[];
  sort: Sort;
}

export const PAGE_SIZE = 24;

export const DEFAULT_FILTERS: Filters = {
  zoneSlug: null,
  operationType: 'SALE',
  propertyType: '',
  bedrooms: '',
  bathrooms: '',
  priceUsdMin: '',
  priceUsdMax: '',
  sqmMin: '',
  sqmMax: '',
  features: [],
  sort: 'recent',
};

const toNum = (s: string): number | undefined => (s ? Number(s) : undefined);

/** Campos comunes (sin paginado ni orden) — los consumen search, forMap y opportunities. */
export function toCommonInput(f: Filters) {
  const bedrooms: number | '5plus' | undefined =
    f.bedrooms === ''
      ? undefined
      : f.bedrooms === '5plus'
        ? ('5plus' as const)
        : Number(f.bedrooms);
  return {
    zoneSlug: f.zoneSlug ?? undefined,
    operationType: f.operationType === '' ? undefined : f.operationType,
    propertyType: f.propertyType === '' ? undefined : f.propertyType,
    bedrooms,
    bathroomsMin: toNum(f.bathrooms),
    priceUsdMin: toNum(f.priceUsdMin),
    priceUsdMax: toNum(f.priceUsdMax),
    sqmMin: toNum(f.sqmMin),
    sqmMax: toNum(f.sqmMax),
    features: f.features,
  };
}

/** Input para `properties.search` (lista paginada). */
export function toSearchInput(f: Filters, offset: number) {
  return {
    ...toCommonInput(f),
    sort: f.sort,
    offset,
    limit: PAGE_SIZE,
  };
}
