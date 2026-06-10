import { z } from 'zod';

import { prisma, type Prisma } from '@inmobi/db';

import { publicProcedure, router } from '../server';
import { buildPropertyWhere, CommonFilters } from './property-filters';

const SortEnum = z.enum(['recent', 'price_asc', 'price_desc']);

const SearchInput = z.object({
  ...CommonFilters,
  sort: SortEnum.default('recent'),
  limit: z.number().int().min(1).max(48).default(24),
  offset: z.number().int().min(0).default(0),
});

const MapInput = z.object(CommonFilters);

// El mapa devuelve TODAS las propiedades que matchean (no pagina), pero con un tope
// duro para no mandar payloads gigantes ni clavar el navegador. Las más recientes
// primero, así el tope conserva lo más relevante.
const MAP_LIMIT = 2000;

export const propertiesRouter = router({
  search: publicProcedure.input(SearchInput).query(async ({ input }) => {
    const where = buildPropertyWhere(input);

    const orderBy: Prisma.PropertyOrderByWithRelationInput[] =
      input.sort === 'price_asc'
        ? [{ priceUsdNormalized: { sort: 'asc', nulls: 'last' } }, { id: 'asc' }]
        : input.sort === 'price_desc'
          ? [{ priceUsdNormalized: { sort: 'desc', nulls: 'last' } }, { id: 'asc' }]
          : [{ lastUpdatedAt: 'desc' }, { id: 'asc' }];

    const [rawItems, total] = await Promise.all([
      prisma.property.findMany({
        where,
        orderBy,
        skip: input.offset,
        take: input.limit,
      }),
      prisma.property.count({ where }),
    ]);

    // Prisma Decimal doesn't serialize cleanly over the wire — convert to strings.
    const items = rawItems.map((p) => ({
      ...p,
      priceAmount: p.priceAmount.toString(),
      priceUsdNormalized: p.priceUsdNormalized?.toString() ?? null,
      expensesAmount: p.expensesAmount?.toString() ?? null,
      totalSqm: p.totalSqm?.toString() ?? null,
      coveredSqm: p.coveredSqm?.toString() ?? null,
      lat: p.lat?.toString() ?? null,
      lng: p.lng?.toString() ?? null,
    }));

    return { items, total, offset: input.offset, limit: input.limit };
  }),

  // Propiedades georreferenciadas para el mapa: mismos filtros que `search`, pero
  // sólo las que tienen lat/lng y devolviendo un payload mínimo (sólo lo que el pin
  // y su popup necesitan). Devuelve también cuántas matchean sin coordenadas todavía,
  // para que el frontend pueda avisar "faltan geocodificar N".
  forMap: publicProcedure.input(MapInput).query(async ({ input }) => {
    const base = buildPropertyWhere(input);
    const withCoords: Prisma.PropertyWhereInput = {
      ...base,
      lat: { not: null },
      lng: { not: null },
    };

    const [rawItems, totalWithCoords, totalAll] = await Promise.all([
      prisma.property.findMany({
        where: withCoords,
        orderBy: [{ lastUpdatedAt: 'desc' }, { id: 'asc' }],
        take: MAP_LIMIT,
        select: {
          id: true,
          url: true,
          title: true,
          portal: true,
          operationType: true,
          propertyType: true,
          priceAmount: true,
          priceCurrency: true,
          priceUsdNormalized: true,
          bedrooms: true,
          bathrooms: true,
          totalSqm: true,
          coveredSqm: true,
          neighborhood: true,
          city: true,
          addressFull: true,
          agencyName: true,
          photos: true,
          lat: true,
          lng: true,
        },
      }),
      prisma.property.count({ where: withCoords }),
      prisma.property.count({ where: base }),
    ]);

    const firstPhoto = (photos: unknown): string | null => {
      if (!Array.isArray(photos)) return null;
      const first = photos[0];
      return typeof first === 'string' ? first : null;
    };

    const items = rawItems
      .map((p) => ({
        id: p.id,
        url: p.url,
        title: p.title,
        portal: p.portal,
        operationType: p.operationType,
        propertyType: p.propertyType,
        priceAmount: p.priceAmount.toString(),
        priceCurrency: p.priceCurrency,
        priceUsdNormalized: p.priceUsdNormalized?.toString() ?? null,
        bedrooms: p.bedrooms,
        bathrooms: p.bathrooms,
        totalSqm: p.totalSqm?.toString() ?? null,
        coveredSqm: p.coveredSqm?.toString() ?? null,
        neighborhood: p.neighborhood,
        city: p.city,
        addressFull: p.addressFull,
        agencyName: p.agencyName,
        photo: firstPhoto(p.photos),
        // lat/lng nunca son null acá (where lo garantiza), pero TS no lo sabe.
        lat: p.lat ? Number(p.lat) : null,
        lng: p.lng ? Number(p.lng) : null,
      }))
      .filter((p): p is typeof p & { lat: number; lng: number } => p.lat !== null && p.lng !== null);

    return {
      items,
      totalWithCoords,
      totalAll,
      capped: totalWithCoords > MAP_LIMIT,
    };
  }),
});
