import { router } from '../server';
import { propertiesRouter } from './properties';

export const appRouter = router({
  properties: propertiesRouter,
});

export type AppRouter = typeof appRouter;
