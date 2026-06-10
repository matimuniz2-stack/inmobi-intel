import { z } from 'zod';

import { type Prisma } from '@inmobi/db';
import { zonesBySlug } from '@inmobi/shared-types';

export const OperationEnum = z.enum(['SALE', 'RENT', 'TEMP_RENT']);
export const PropertyTypeEnum = z.enum(['APT', 'HOUSE', 'PH', 'LOCAL', 'TERRENO', 'OTRO']);

const BedroomsFilter = z.union([z.number().int().min(1).max(20), z.literal('5plus')]);

/**
 * Características sin columna propia en la DB (amenities está vacía hasta T10):
 * se buscan como mención textual en el aviso (título hoy; description se suma
 * sola cuando el scraper la pueble). Cada key lista sus variantes de redacción;
 * el matching es case-insensitive pero NO accent-insensitive, por eso las
 * variantes con y sin tilde se listan explícitas.
 */
export const FEATURE_KEYWORDS = {
  cochera: ['cochera', 'garage', 'garaje'],
  quincho: ['quincho'],
  pileta: ['pileta', 'piscina'],
  parrilla: ['parrilla'],
  balcon: ['balcon', 'balcón'],
  terraza: ['terraza'],
  patio: ['patio'],
  jardin: ['jardin', 'jardín'],
  vista_al_mar: ['vista al mar', 'frente al mar', 'vista mar'],
  a_estrenar: ['estrenar'],
  apto_credito: ['apto credito', 'apto crédito', 'apto banco'],
  amoblado: ['amoblado', 'amueblado'],
} as const;

export type FeatureKey = keyof typeof FEATURE_KEYWORDS;

const FeatureEnum = z.enum(
  Object.keys(FEATURE_KEYWORDS) as [FeatureKey, ...FeatureKey[]],
);

/** Filtros de propiedad comunes a búsqueda, mapa y oportunidades. */
export const CommonFilters = {
  zoneSlug: z.string().min(1).optional(),
  operationType: OperationEnum.optional(),
  propertyType: PropertyTypeEnum.optional(),
  bedrooms: BedroomsFilter.optional(),
  bathroomsMin: z.number().int().min(1).max(10).optional(),
  priceUsdMin: z.number().nonnegative().optional(),
  priceUsdMax: z.number().nonnegative().optional(),
  sqmMin: z.number().nonnegative().optional(),
  sqmMax: z.number().nonnegative().optional(),
  features: z.array(FeatureEnum).max(12).default([]),
};

const CommonFiltersObject = z.object(CommonFilters);
export type CommonFilterInput = z.infer<typeof CommonFiltersObject>;

/**
 * Traduce los filtros a un `where` de Prisma. Resuelve la zona elegida a un filtro
 * (city, neighborhood?):
 * - Zona con mlNeighborhood: barrio exacto dentro de la ciudad (barrios CABA y MdP).
 * - Zona con sólo mlCity: filtra por ciudad (catch-all de MdP y alrededores).
 * - Sin zona: sin filtro espacial.
 *
 * Cada característica exige al menos una mención (OR de variantes, sobre título
 * y descripción); pedir varias es un AND.
 */
export function buildPropertyWhere(input: CommonFilterInput): Prisma.PropertyWhereInput {
  const zone = input.zoneSlug ? zonesBySlug.get(input.zoneSlug) : null;
  const zoneFilter: Prisma.PropertyWhereInput = zone
    ? zone.mlNeighborhood
      ? {
          neighborhood: { equals: zone.mlNeighborhood, mode: 'insensitive' },
          city: { equals: zone.mlCity, mode: 'insensitive' },
        }
      : { city: { equals: zone.mlCity, mode: 'insensitive' } }
    : {};

  const featureFilters: Prisma.PropertyWhereInput[] = (input.features ?? []).map(
    (feature) => ({
      OR: FEATURE_KEYWORDS[feature].flatMap((kw) => [
        { title: { contains: kw, mode: 'insensitive' as const } },
        { description: { contains: kw, mode: 'insensitive' as const } },
      ]),
    }),
  );

  return {
    isActive: true,
    ...zoneFilter,
    ...(input.operationType ? { operationType: input.operationType } : {}),
    ...(input.propertyType ? { propertyType: input.propertyType } : {}),
    ...(input.bedrooms !== undefined
      ? input.bedrooms === '5plus'
        ? { bedrooms: { gte: 5 } }
        : { bedrooms: input.bedrooms }
      : {}),
    ...(input.bathroomsMin !== undefined ? { bathrooms: { gte: input.bathroomsMin } } : {}),
    ...(input.priceUsdMin !== undefined || input.priceUsdMax !== undefined
      ? {
          priceUsdNormalized: {
            ...(input.priceUsdMin !== undefined ? { gte: input.priceUsdMin } : {}),
            ...(input.priceUsdMax !== undefined ? { lte: input.priceUsdMax } : {}),
          },
        }
      : {}),
    ...(input.sqmMin !== undefined || input.sqmMax !== undefined
      ? {
          totalSqm: {
            ...(input.sqmMin !== undefined ? { gte: input.sqmMin } : {}),
            ...(input.sqmMax !== undefined ? { lte: input.sqmMax } : {}),
          },
        }
      : {}),
    ...(featureFilters.length > 0 ? { AND: featureFilters } : {}),
  };
}
