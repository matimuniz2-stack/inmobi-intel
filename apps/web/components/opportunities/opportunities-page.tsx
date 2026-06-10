'use client';

import { ChevronLeft, ChevronRight, Loader2, Search, SlidersHorizontal } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import {
  DEFAULT_FILTERS,
  PAGE_SIZE,
  toCommonInput,
  type Filters,
} from '@/components/search/filters';
import { FiltersPanel } from '@/components/search/filters-panel';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { trpc } from '@/lib/trpc/client';
import { cn } from '@/lib/utils';

import { OpportunityCard } from './opportunity-card';

type MinScore = '' | '35' | '60';

// En oportunidades el default es "todas las operaciones": la lista curada ya es
// chica y el usuario quiere ver todo lo que el detector marcó.
const OPPORTUNITY_DEFAULTS: Filters = { ...DEFAULT_FILTERS, operationType: '' };

export function OpportunitiesPage() {
  const [filters, setFilters] = React.useState<Filters>(OPPORTUNITY_DEFAULTS);
  const [minScore, setMinScore] = React.useState<MinScore>('');
  const [page, setPage] = React.useState(0);
  const [filtersOpenMobile, setFiltersOpenMobile] = React.useState(false);

  const offset = page * PAGE_SIZE;
  const query = trpc.opportunities.list.useQuery(
    {
      ...toCommonInput(filters),
      minScore: minScore === '' ? undefined : Number(minScore),
      offset,
      limit: PAGE_SIZE,
    },
    { placeholderData: (prev) => prev },
  );

  React.useEffect(() => {
    setPage(0);
  }, [filters, minScore]);

  const updateFilter = <K extends keyof Filters>(k: K, v: Filters[K]) =>
    setFilters((f) => ({ ...f, [k]: v }));

  const resetFilters = () => {
    setFilters(OPPORTUNITY_DEFAULTS);
    setMinScore('');
  };

  const totalPages = query.data ? Math.ceil(query.data.total / PAGE_SIZE) : 0;

  return (
    <div className="min-h-dvh">
      <header className="border-b bg-card">
        <div className="container flex items-center justify-between py-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight">Inmobi Intel</h1>
            <p className="text-sm text-muted-foreground">Oportunidades del día</p>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm">
              <Link href="/buscar">
                <Search className="mr-2 h-4 w-4" />
                Búsqueda
              </Link>
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="md:hidden"
              onClick={() => setFiltersOpenMobile((v) => !v)}
            >
              <SlidersHorizontal className="mr-2 h-4 w-4" />
              Filtros
            </Button>
          </div>
        </div>
      </header>

      <main className="container py-4 md:py-6">
        <div className="grid gap-6 md:grid-cols-[280px_1fr]">
          <aside className={cn('space-y-4', !filtersOpenMobile && 'hidden md:block')}>
            <FiltersPanel
              filters={filters}
              updateFilter={updateFilter}
              onReset={resetFilters}
              footer={
                <div className="space-y-2">
                  <Label htmlFor="minscore">Fuerza de la oportunidad</Label>
                  <select
                    id="minscore"
                    value={minScore}
                    onChange={(e) => setMinScore(e.target.value as MinScore)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <option value="">Todas</option>
                    <option value="35">Buenas (score 35+)</option>
                    <option value="60">Fuertes (score 60+)</option>
                  </select>
                </div>
              }
            />
          </aside>

          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm text-muted-foreground">
                {query.isPending ? (
                  <span className="inline-flex items-center gap-2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Buscando oportunidades...
                  </span>
                ) : query.data ? (
                  <>
                    <strong className="text-foreground">{query.data.total}</strong>{' '}
                    {query.data.total === 1 ? 'oportunidad' : 'oportunidades'}
                  </>
                ) : null}
                {query.isFetching && !query.isPending && (
                  <span className="ml-2 text-xs">· actualizando…</span>
                )}
              </div>
            </div>

            {query.isError && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
                Error al cargar oportunidades: {query.error.message}
              </div>
            )}

            {query.isPending ? (
              <ResultsSkeleton />
            ) : query.data && query.data.items.length === 0 ? (
              <EmptyState />
            ) : (
              <>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {query.data?.items.map((o) => (
                    <OpportunityCard key={o.id} o={o} />
                  ))}
                </div>

                {totalPages > 1 && (
                  <nav className="flex items-center justify-center gap-2 pt-4">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage((p) => Math.max(0, p - 1))}
                      disabled={page === 0 || query.isFetching}
                    >
                      <ChevronLeft className="mr-1 h-4 w-4" /> Anterior
                    </Button>
                    <span className="px-2 text-sm text-muted-foreground">
                      Página {page + 1} de {totalPages}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setPage((p) => p + 1)}
                      disabled={page + 1 >= totalPages || query.isFetching}
                    >
                      Siguiente <ChevronRight className="ml-1 h-4 w-4" />
                    </Button>
                  </nav>
                )}
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

function ResultsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="overflow-hidden rounded-lg border bg-card">
          <Skeleton className="aspect-[4/3] rounded-none" />
          <div className="space-y-2 p-4">
            <Skeleton className="h-5 w-1/2" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-16 w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border bg-card py-12 text-center">
      <p className="text-sm font-semibold">Sin oportunidades que matcheen</p>
      <p className="max-w-md text-sm text-muted-foreground">
        El detector arma la lista cada mañana sobre la data scrapeada. Probá ampliar la zona o
        bajar el score mínimo. Si recién pusiste a correr el scraper, esperá al próximo scoreo.
      </p>
    </div>
  );
}
