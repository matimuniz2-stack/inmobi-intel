'use client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

import {
  FEATURE_OPTIONS,
  type BathroomsFilter,
  type BedroomsFilter,
  type FeatureKey,
  type Filters,
  type Operation,
  type PropertyType,
} from './filters';
import { ZoneCombobox } from './zone-combobox';

const selectClass =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/**
 * Panel de filtros reutilizable. Lo comparten /buscar, /mapa y /oportunidades, así
 * un solo lugar define los controles de zona/operación/tipo/dormitorios/baños/
 * precio/superficie/características. `footer` permite que cada página agregue sus
 * controles propios (p. ej. score mínimo en oportunidades).
 */
export function FiltersPanel({
  filters,
  updateFilter,
  onReset,
  footer,
}: {
  filters: Filters;
  updateFilter: <K extends keyof Filters>(k: K, v: Filters[K]) => void;
  onReset: () => void;
  footer?: React.ReactNode;
}) {
  const toggleFeature = (key: FeatureKey) => {
    const next = filters.features.includes(key)
      ? filters.features.filter((f) => f !== key)
      : [...filters.features, key];
    updateFilter('features', next);
  };

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
          className={selectClass}
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
          className={selectClass}
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

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-2">
          <Label htmlFor="bedrooms">Dormitorios</Label>
          <select
            id="bedrooms"
            value={filters.bedrooms}
            onChange={(e) => updateFilter('bedrooms', e.target.value as BedroomsFilter)}
            className={selectClass}
          >
            <option value="">Cualq.</option>
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3</option>
            <option value="4">4</option>
            <option value="5plus">5+</option>
          </select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="bathrooms">Baños</Label>
          <select
            id="bathrooms"
            value={filters.bathrooms}
            onChange={(e) => updateFilter('bathrooms', e.target.value as BathroomsFilter)}
            className={selectClass}
          >
            <option value="">Cualq.</option>
            <option value="1">1+</option>
            <option value="2">2+</option>
            <option value="3">3+</option>
          </select>
        </div>
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

      <div className="space-y-2">
        <Label>Superficie (m²)</Label>
        <div className="grid grid-cols-2 gap-2">
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            value={filters.sqmMin}
            onChange={(e) => updateFilter('sqmMin', e.target.value)}
            placeholder="Min"
          />
          <Input
            type="number"
            inputMode="numeric"
            min={0}
            value={filters.sqmMax}
            onChange={(e) => updateFilter('sqmMax', e.target.value)}
            placeholder="Max"
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label>Características</Label>
        <div className="flex flex-wrap gap-1.5">
          {FEATURE_OPTIONS.map(({ key, label }) => {
            const active = filters.features.includes(key);
            return (
              <button
                key={key}
                type="button"
                onClick={() => toggleFeature(key)}
                aria-pressed={active}
                className={cn(
                  'rounded-full border px-2.5 py-1 text-xs transition-colors',
                  active
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-input bg-background text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                )}
              >
                {label}
              </button>
            );
          })}
        </div>
        <p className="text-[11px] leading-snug text-muted-foreground">
          Busca avisos que mencionan la característica. Un aviso que la tiene pero no
          la menciona puede quedar afuera.
        </p>
      </div>

      {footer}
    </div>
  );
}
