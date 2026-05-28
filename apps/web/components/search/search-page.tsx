'use client';

import { ChevronLeft, ChevronRight, Loader2, SlidersHorizontal } from 'lucide-react';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { trpc } from '@/lib/trpc/client';
import { cn } from '@/lib/utils';

import { PropertyCard } from './property-card';
import { ZoneCombobox } from './zone-combobox';

type Operation = 'SALE' | 'RENT' | 'TEMP_RENT' | '';
type PropertyType = 'APT' | 'HOUSE' | 'PH' | 'LOCAL' | 'TERRENO' | 'OTRO' | '';

interface Filters {
  zoneSlug: string | null;
  operationType: Operation;
  propertyType: PropertyType;
  bedroomsMin: string;
  priceUsdMin: string;
  priceUsdMax: string;
}

const PAGE_SIZE = 24;

const DEFAULT_FILTERS: Filters = {
  zoneSlug: null,
  operationType: 'SALE',
  propertyType: '',
  bedroomsMin: '',
  priceUsdMin: '',
  priceUsdMax: '',
};

function toQueryInput(f: Filters, offset: number) {
  return {
    zoneSlug: f.zoneSlug ?? undefined,
    operationType: f.operationType === '' ? undefined : f.operationType,
    propertyType: f.propertyType === '' ? undefined : f.propertyType,
    bedroomsMin: f.bedroomsMin ? Number(f.bedroomsMin) : undefined,
    priceUsdMin: f.priceUsdMin ? Number(f.priceUsdMin) : undefined,
    priceUsdMax: f.priceUsdMax ? Number(f.priceUsdMax) : undefined,
    offset,
    limit: PAGE_SIZE,
  };
}

export function SearchPage() {
  const [filters, setFilters] = React.useState<Filters>(DEFAULT_FILTERS);
  const [page, setPage] = React.useState(0);
  const [filtersOpenMobile, setFiltersOpenMobile] = React.useState(false);

  const offset = page * PAGE_SIZE;
  const query = trpc.properties.search.useQuery(toQueryInput(filters, offset), {
    placeholderData: (prev) => prev,
  });

  // Reset page when filters change
  React.useEffect(() => {
    setPage(0);
  }, [
    filters.zoneSlug,
    filters.operationType,
    filters.propertyType,
    filters.bedroomsMin,
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
            <div className="flex items-center justify-between">
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
              </div>
              {query.isFetching && !query.isPending && (
                <span className="text-xs text-muted-foreground">Actualizando…</span>
              )}
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

function FiltersPanel({
  filters,
  updateFilter,
  onReset,
}: {
  filters: Filters;
  updateFilter: <K extends keyof Filters>(k: K, v: Filters[K]) => void;
  onReset: () => void;
}) {
  return (
    <div className="space-y-4 rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Filtros</h2>
        <Button variant="ghost" size="sm" onClick={onReset} className="h-7 text-xs">
          Limpiar
        </Button>
      </div>

      <div className="space-y-2">
        <Label>Zona</Label>
        <ZoneCombobox
          value={filters.zoneSlug}
          onChange={(slug) => updateFilter('zoneSlug', slug)}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="operation">Operación</Label>
        <select
          id="operation"
          value={filters.operationType}
          onChange={(e) => updateFilter('operationType', e.target.value as Operation)}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Todas</option>
          <option value="SALE">Venta</option>
          <option value="RENT">Alquiler</option>
          <option value="TEMP_RENT">Alq. temporal</option>
        </select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="ptype">Tipo de propiedad</Label>
        <select
          id="ptype"
          value={filters.propertyType}
          onChange={(e) => updateFilter('propertyType', e.target.value as PropertyType)}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Todos</option>
          <option value="APT">Departamento</option>
          <option value="HOUSE">Casa</option>
          <option value="PH">PH</option>
          <option value="LOCAL">Local</option>
          <option value="TERRENO">Terreno</option>
          <option value="OTRO">Otro</option>
        </select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="bedrooms">Ambientes (mínimo)</Label>
        <Input
          id="bedrooms"
          type="number"
          inputMode="numeric"
          min={0}
          max={20}
          value={filters.bedroomsMin}
          onChange={(e) => updateFilter('bedroomsMin', e.target.value)}
          placeholder="cualquiera"
        />
      </div>

      <div className="space-y-2">
        <Label>Precio (USD)</Label>
        <div className="grid grid-cols-2 gap-2">
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            value={filters.priceUsdMin}
            onChange={(e) => updateFilter('priceUsdMin', e.target.value)}
            placeholder="Min"
          />
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            value={filters.priceUsdMax}
            onChange={(e) => updateFilter('priceUsdMax', e.target.value)}
            placeholder="Max"
          />
        </div>
      </div>
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
