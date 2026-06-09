'use client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import type { Filters, Operation, PropertyType, BedroomsFilter } from './filters';
import { ZoneCombobox } from './zone-combobox';

/**
 * Panel de filtros reutilizable. Lo comparten la búsqueda en lista y el mapa, así un
 * solo lugar define los controles de zona/operación/tipo/ambientes/precio.
 */
export function FiltersPanel({
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
        <Label htmlFor="bedrooms">Ambientes</Label>
        <select
          id="bedrooms"
          value={filters.bedrooms}
          onChange={(e) => updateFilter('bedrooms', e.target.value as BedroomsFilter)}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Cualquiera</option>
          <option value="1">1 (monoambiente)</option>
          <option value="2">2</option>
          <option value="3">3</option>
          <option value="4">4</option>
          <option value="5plus">5 o más</option>
        </select>
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
