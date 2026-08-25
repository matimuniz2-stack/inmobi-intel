'use client';

import { Check, ChevronsUpDown, X } from 'lucide-react';
import * as React from 'react';

import { findZonesByQuery, zones, type Zone } from '@inmobi/shared-types/zones';

import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

interface Props {
  /** Slugs seleccionados. Vacío = cualquier zona. */
  value: string[];
  onChange: (slugs: string[]) => void;
  placeholder?: string;
}

/**
 * Multi-select de zonas/barrios: cada click agrega o quita una zona y el popover
 * queda abierto para seguir sumando. El botón resume la selección; los chips
 * removibles los dibuja el FiltersPanel debajo.
 */
export function ZoneCombobox({ value, onChange, placeholder = 'Cualquier zona' }: Props) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState('');

  const filtered = React.useMemo(
    () => (query.trim() ? findZonesByQuery(query, 30) : [...zones]),
    [query],
  );

  const groups = React.useMemo(() => {
    const mdp = filtered.filter(
      (z) => z.province === 'Buenos Aires' && z.mlCity === 'Mar del Plata',
    );
    const alrededores = filtered.filter(
      (z) => z.province === 'Buenos Aires' && z.mlCity !== 'Mar del Plata',
    );
    const caba = filtered.filter((z) => z.province === 'CABA');
    return { mdp, alrededores, caba };
  }, [filtered]);

  const toggle = (slug: string) => {
    onChange(
      value.includes(slug) ? value.filter((s) => s !== slug) : [...value, slug],
    );
    setQuery('');
  };

  const label =
    value.length === 0
      ? placeholder
      : value.length === 1
        ? (zones.find((z) => z.slug === value[0])?.displayName ?? value[0])
        : `${value.length} zonas`;

  const renderGroup = (heading: string, items: Zone[]) =>
    items.length > 0 && (
      <CommandGroup heading={heading}>
        {items.map((z) => (
          <CommandItem key={z.slug} value={z.slug} onSelect={() => toggle(z.slug)}>
            <Check
              className={cn(
                'mr-2 h-4 w-4',
                value.includes(z.slug) ? 'opacity-100' : 'opacity-0',
              )}
            />
            {z.displayName}
          </CommandItem>
        ))}
      </CommandGroup>
    );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal"
        >
          <span className={cn('truncate', value.length === 0 && 'text-muted-foreground')}>
            {label}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Tipea zona o barrio..."
            value={query}
            onValueChange={setQuery}
          />
          <CommandList>
            <CommandEmpty>Sin coincidencias.</CommandEmpty>
            {value.length > 0 && (
              <CommandGroup>
                <CommandItem
                  value="__clear__"
                  onSelect={() => {
                    onChange([]);
                    setOpen(false);
                    setQuery('');
                  }}
                  className="text-muted-foreground"
                >
                  <X className="mr-2 h-4 w-4" />
                  Quitar todas ({value.length})
                </CommandItem>
              </CommandGroup>
            )}
            {renderGroup('Mar del Plata + barrios', groups.mdp)}
            {renderGroup('Alrededores', groups.alrededores)}
            {renderGroup('CABA', groups.caba)}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
