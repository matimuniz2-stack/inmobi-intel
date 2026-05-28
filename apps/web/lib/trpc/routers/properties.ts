import { z } from 'zod';

import { prisma, type Prisma } from '@inmobi/db';
import { zonesBySlug } from '@inmobi/shared-types';

import { publicProcedure, router } from '../server';

const OperationEnum = z.enum(['SALE', 'RENT', 'TEMP_RENT']);
const PropertyTypeEnum = z.enum(['APT', 'HOUSE', 'PH', 'LOCAL', 'TERRENO', 'OTRO']);

const SearchInput = z.object({
  zoneSlug: z.string().min(1).optional(),
  operationType: OperationEnum.optional(),
  propertyType: PropertyTypeEnum.optional(),
  bedroomsMin: z.number().int().min(0).max(20).optional(),
  priceUsdMin: z.number().nonnegative().optional(),
  priceUsdMax: z.number().nonnegative().optional(),
  limit: z.number().int().min(1).max(48).default(24),
  offset: z.number().int().min(0).default(0),
});

export const propertiesRouter = router({
  search: publicProcedure.input(SearchInput).query(async ({ input }) => {
    // Resolve the selected zone to a (city, neighborhood?) filter.
    // - Zone w/ mlNeighborhood: filter by exact neighborhood within the city
    //   (CABA barrios + MdP barrios both use this path)
    // - Zone w/ only mlCity: filter by city (catch-all for MdP and its surroundings)
    // - No zone: no spatial filter
    const zone = input.zoneSlug ? zonesBySlug.get(input.zoneSlug) : null;
    const zoneFilter: Prisma.PropertyWhereInput = zone
      ? zone.mlNeighborhood
        ? {
            neighborhood: { equals: zone.mlNeighborhood, mode: 'insensitive' },
            city: { equals: zone.mlCity, mode: 'insensitive' },
          }
        : { city: { equals: zone.mlCity, mode: 'insensitive' } }
      : {};

    const where: Prisma.PropertyWhereInput = {
      isActive: true,
      ...zoneFilter,
      ...(input.operationType ? { operationType: input.operationType } : {}),
      ...(input.propertyType ? { propertyType: input.propertyType } : {}),
      ...(input.bedroomsMin !== undefined
        ? { bedrooms: { gte: input.bedroomsMin } }
        : {}),
      ...(input.priceUsdMin !== undefined || input.priceUsdMax !== undefined
        ? {
            priceUsdNormalized: {
              ...(input.priceUsdMin !== undefined ? { gte: input.priceUsdMin } : {}),
              ...(input.priceUsdMax !== undefined ? { lte: input.priceUsdMax } : {}),
            },
          }
        : {}),
    };

    const [rawItems, total] = await Promise.all([
      prisma.property.findMany({
        where,
        orderBy: [{ lastUpdatedAt: 'desc' }, { id: 'asc' }],
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
});
