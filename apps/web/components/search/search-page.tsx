'use client';

import { ChevronLeft, ChevronRight, Flame, Loader2, Map, SlidersHorizontal } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { trpc } from '@/lib/trpc/client';
import { cn } from '@/lib/utils';

import { DEFAULT_FILTERS, PAGE_SIZE, toSearchInput, type Filters, type Sort } from './filters';
import { FiltersPanel } from './filters-panel';
import { PropertyCard } from './property-card';

export function SearchPage() {
  const [filters, setFilters] = React.useState<Filters>(DEFAULT_FILTERS);
  const [page, setPage] = React.useState(0);
  const [filtersOpenMobile, setFiltersOpenMobile] = React.useState(false);

  const offset = page * PAGE_SIZE;
  const query = trpc.properties.search.useQuery(toSearchInput(filters, offset), {
    placeholderData: (prev) => prev,
  });

  // Reset page when filters change
  React.useEffect(() => {
    setPage(0);
  }, [
    filters.zoneSlug,
    filters.operationType,
    filters.propertyType,
    filters.bedrooms,
    filters.priceUsdMin,
    filters.priceUsdMax,
  ]);

  const updateFilter = <K extends keyof Filters>(k: K, v: Filters[K]) =>
    setFilters((f) => ({ ...f, [k]: v }));

  const resetFilters = () => setFilters(DEFAULT_FILTERS);

  const totalPages = query.data ? Math.ceil(query.data.total / PAGE_SIZE) : 0;

  return (
    <div className="min-h-dvh">
      <header className="border-b bg-card">
        <div className="container flex items-center justify-between py-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight">Inmobi Intel</h1>
            <p className="text-sm text-muted-foreground">Búsqueda Reversa</p>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild variant="ghost" size="sm">
              <Link href="/mapa">
                <Map className="mr-2 h-4 w-4" />
                Mapa
              </Link>
            </Button>
            <Button asChild variant="ghost" size="sm">
              <Link href="/oportunidades">
                <Flame className="mr-2 h-4 w-4" />
                Oportunidades
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
          <aside
            className={cn(
              'space-y-4',
              !filtersOpenMobile && 'hidden md:block',
            )}
          >
            <FiltersPanel
              filters={filters}
              updateFilter={updateFilter}
              onReset={resetFilters}
            />
          </aside>

          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm text-muted-foreground">
                {query.isPending ? (
                  <span className="inline-flex items-center gap-2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Buscando...
                  </span>
                ) : query.data ? (
                  <>
                    <strong className="text-foreground">{query.data.total}</strong>{' '}
                    {query.data.total === 1 ? 'propiedad' : 'propiedades'}
                  </>
                ) : null}
                {query.isFetching && !query.isPending && (
                  <span className="ml-2 text-xs">· actualizando…</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Label htmlFor="sort" className="text-xs text-muted-foreground">
                  Ordenar por
                </Label>
                <select
                  id="sort"
                  value={filters.sort}
                  onChange={(e) => updateFilter('sort', e.target.value as Sort)}
                  className="h-8 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="recent">Más recientes</option>
                  <option value="price_asc">Precio: menor a mayor</option>
                  <option value="price_desc">Precio: mayor a menor</option>
                </select>
              </div>
            </div>

            {query.isError && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
                Error al buscar: {query.error.message}
              </div>
            )}

            {query.isPending ? (
              <ResultsSkeleton />
            ) : query.data && query.data.items.length === 0 ? (
              <EmptyState />
            ) : (
              <>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {query.data?.items.map((p) => (
                    <PropertyCard key={p.id} p={p} />
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
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-8 w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border bg-card py-12 text-center">
      <p className="text-sm font-semibold">Sin propiedades que matcheen</p>
      <p className="text-sm text-muted-foreground">
        Probá afinar los filtros (ampliar rango de precio, sacar tipo de propiedad).
      </p>
    </div>
  );
}
