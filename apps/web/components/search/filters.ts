/** Tipos y helpers de filtros compartidos entre la búsqueda en lista (/buscar) y el mapa (/mapa). */

export type Operation = 'SALE' | 'RENT' | 'TEMP_RENT' | '';
export type PropertyType = 'APT' | 'HOUSE' | 'PH' | 'LOCAL' | 'TERRENO' | 'OTRO' | '';
export type Sort = 'recent' | 'price_asc' | 'price_desc';
export type BedroomsFilter = '' | '1' | '2' | '3' | '4' | '5plus';

export interface Filters {
  zoneSlug: string | null;
  operationType: Operation;
  propertyType: PropertyType;
  bedrooms: BedroomsFilter;
  priceUsdMin: string;
  priceUsdMax: string;
  sort: Sort;
}

export const PAGE_SIZE = 24;

export const DEFAULT_FILTERS: Filters = {
  zoneSlug: null,
  operationType: 'SALE',
  propertyType: '',
  bedrooms: '',
  priceUsdMin: '',
  priceUsdMax: '',
  sort: 'recent',
};

/** Campos comunes (sin paginado ni orden) — los consume tanto search como forMap. */
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
    priceUsdMin: f.priceUsdMin ? Number(f.priceUsdMin) : undefined,
    priceUsdMax: f.priceUsdMax ? Number(f.priceUsdMax) : undefined,
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
