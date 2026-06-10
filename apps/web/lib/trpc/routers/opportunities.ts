import { z } from 'zod';

import { prisma, type Prisma } from '@inmobi/db';

import { publicProcedure, router } from '../server';
import { buildPropertyWhere, CommonFilters } from './property-filters';

const ListInput = z.object({
  ...CommonFilters,
  minScore: z.number().int().min(0).max(100).optional(),
  limit: z.number().int().min(1).max(48).default(24),
  offset: z.number().int().min(0).default(0),
});

export const opportunitiesRouter = router({
  // Lista curada de oportunidades, rankeadas por score. Misma traducción de filtros
  // de propiedad que la búsqueda reversa y el mapa (zona, precio, dormitorios,
  // baños, superficie, características).
  list: publicProcedure.input(ListInput).query(async ({ input }) => {
    const propertyFilter = buildPropertyWhere(input);

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
