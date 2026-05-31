import { router } from '../server';
import { opportunitiesRouter } from './opportunities';
import { propertiesRouter } from './properties';

export const appRouter = router({
  properties: propertiesRouter,
  opportunities: opportunitiesRouter,
});

export type AppRouter = typeof appRouter;
