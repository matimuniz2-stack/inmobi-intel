import { z } from 'zod';

import { prisma, type Prisma } from '@inmobi/db';
import { zonesBySlug } from '@inmobi/shared-types';

import { publicProcedure, router } from '../server';

const OperationEnum = z.enum(['SALE', 'RENT', 'TEMP_RENT']);
const PropertyTypeEnum = z.enum(['APT', 'HOUSE', 'PH', 'LOCAL', 'TERRENO', 'OTRO']);

const ListInput = z.object({
  zoneSlug: z.string().min(1).optional(),
  operationType: OperationEnum.optional(),
  propertyType: PropertyTypeEnum.optional(),
  minScore: z.number().int().min(0).max(100).optional(),
  limit: z.number().int().min(1).max(48).default(24),
  offset: z.number().int().min(0).default(0),
});

export const opportunitiesRouter = router({
  // Lista curada de oportunidades, rankeadas por score. Mismo criterio de zona que
  // la búsqueda reversa: barrio exacto si la zona lo define, ciudad si es catch-all.
  list: publicProcedure.input(ListInput).query(async ({ input }) => {
    const zone = input.zoneSlug ? zonesBySlug.get(input.zoneSlug) : null;
    const zoneFilter: Prisma.PropertyWhereInput = zone
      ? zone.mlNeighborhood
        ? {
            neighborhood: { equals: zone.mlNeighborhood, mode: 'insensitive' },
            city: { equals: zone.mlCity, mode: 'insensitive' },
          }
        : { city: { equals: zone.mlCity, mode: 'insensitive' } }
      : {};

    const propertyFilter: Prisma.PropertyWhereInput = {
      isActive: true,
      ...zoneFilter,
      ...(input.operationType ? { operationType: input.operationType } : {}),
      ...(input.propertyType ? { propertyType: input.propertyType } : {}),
    };

    const where: Prisma.OpportunityWhereInput = {
      ...(input.minScore !== undefined ? { score: { gte: input.minScore } } : {}),
      property: propertyFilter,
    };

    const [rawItems, total] = await Promise.all([
      prisma.opportunity.findMany({
        where,
        include: { property: true },
        orderBy: [{ score: 'desc' }, { computedAt: 'desc' }],
        skip: input.offset,
        take: input.limit,
      }),
      prisma.opportunity.count({ where }),
    ]);

    // Prisma Decimal no serializa limpio por el wire — pasamos a strings.
    const items = rawItems.map((o) => ({
      id: o.id,
      score: o.score,
      reasons: o.reasons,
      computedAt: o.computedAt,
      priceUsdAtScore: o.priceUsdAtScore?.toString() ?? null,
      property: {
        ...o.property,
        priceAmount: o.property.priceAmount.toString(),
        priceUsdNormalized: o.property.priceUsdNormalized?.toString() ?? null,
        expensesAmount: o.property.expensesAmount?.toString() ?? null,
        totalSqm: o.property.totalSqm?.toString() ?? null,
        coveredSqm: o.property.coveredSqm?.toString() ?? null,
        lat: o.property.lat?.toString() ?? null,
        lng: o.property.lng?.toString() ?? null,
      },
    }));

    return { items, total, offset: input.offset, limit: input.limit };
  }),
});
