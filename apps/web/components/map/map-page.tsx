'use client';

import { ArrowLeft, Loader2, MapPin, SlidersHorizontal } from 'lucide-react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import * as React from 'react';

import { FiltersPanel } from '@/components/search/filters-panel';
import { DEFAULT_FILTERS, toCommonInput, type Filters } from '@/components/search/filters';
import { Button } from '@/components/ui/button';
import { trpc } from '@/lib/trpc/client';
import { cn } from '@/lib/utils';

import type { MapPoint } from './leaflet-map';

// Leaflet toca `window` al inicializarse → sólo en el cliente, sin SSR.
const LeafletMap = dynamic(() => import('./leaflet-map'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center bg-muted">
      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
    </div>
  ),
});

const LEGEND: { label: string; color: string }[] = [
  { label: 'Venta', color: '#059669' },
  { label: 'Alquiler', color: '#2563eb' },
  { label: 'Temporal', color: '#d97706' },
];

export function MapPage() {
  const [filters, setFilters] = React.useState<Filters>(DEFAULT_FILTERS);
  const [filtersOpenMobile, setFiltersOpenMobile] = React.useState(false);

  const query = trpc.properties.forMap.useQuery(toCommonInput(filters), {
    placeholderData: (prev) => prev,
  });

  const updateFilter = <K extends keyof Filters>(k: K, v: Filters[K]) =>
    setFilters((f) => ({ ...f, [k]: v }));
  const resetFilters = () => setFilters(DEFAULT_FILTERS);

  const points: MapPoint[] = query.data?.items ?? [];
  const withCoords = query.data?.totalWithCoords ?? 0;
  const totalAll = query.data?.totalAll ?? 0;
  const missing = Math.max(0, totalAll - withCoords);

  return (
    <div className="flex h-dvh flex-col">
      <header className="z-[1100] border-b bg-card">
        <div className="container flex items-center justify-between gap-2 py-3">
          <div className="flex items-center gap-3">
            <Button asChild variant="ghost" size="sm">
              <Link href="/buscar">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Lista
              </Link>
            </Button>
            <div>
              <h1 className="text-base font-bold leading-tight tracking-tight">Mapa</h1>
              <p className="text-xs text-muted-foreground">
                {query.isPending ? (
                  <span className="inline-flex items-center gap-1">
                    <Loader2 className="h-3 w-3 animate-spin" /> cargando…
                  </span>
                ) : (
                  <>
                    <strong className="text-foreground">{withCoords}</strong> en el mapa
                    {missing > 0 && (
                      <span className="ml-1">· {missing} sin ubicar todavía</span>
                    )}
                    {query.data?.capped && <span className="ml-1">· (tope 2000)</span>}
                  </>
                )}
              </p>
            </div>
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

      <div className="relative grid min-h-0 flex-1 md:grid-cols-[300px_1fr]">
        <aside
          className={cn(
            'overflow-y-auto border-r bg-card p-4',
            // En desktop es una columna fija; en mobile, overlay sobre el mapa.
            filtersOpenMobile
              ? 'absolute inset-0 z-[1050] md:static md:z-auto'
              : 'hidden md:block',
          )}
        >
          <div className="space-y-4">
            <FiltersPanel
              filters={filters}
              updateFilter={updateFilter}
              onReset={resetFilters}
            />
            <Legend />
            {filtersOpenMobile && (
              <Button
                className="w-full md:hidden"
                onClick={() => setFiltersOpenMobile(false)}
              >
                Ver mapa
              </Button>
            )}
          </div>
        </aside>

        <div className="relative min-h-0">
          {query.data && points.length === 0 && !query.isPending && (
            <div className="pointer-events-none absolute inset-x-0 top-4 z-[1000] flex justify-center">
              <div className="pointer-events-auto rounded-md border bg-card px-4 py-2 text-sm shadow-md">
                {totalAll === 0 ? (
                  <span className="text-muted-foreground">
                    No hay propiedades que matcheen estos filtros.
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                    <MapPin className="h-3.5 w-3.5" />
                    {totalAll} propiedades, pero ninguna geocodificada todavía.
                  </span>
                )}
              </div>
            </div>
          )}
          <LeafletMap points={points} />
        </div>
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="rounded-lg border bg-card p-3">
      <h3 className="mb-2 text-xs font-semibold text-muted-foreground">Referencias</h3>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {LEGEND.map((l) => (
          <span key={l.label} className="inline-flex items-center gap-1.5 text-xs">
            <span
              className="inline-block h-3 w-3 rounded-full border border-white shadow-sm"
              style={{ backgroundColor: l.color }}
            />
            {l.label}
          </span>
        ))}
      </div>
    </div>
  );
}
