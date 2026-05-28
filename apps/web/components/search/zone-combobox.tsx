'use client';

import { Check, ChevronsUpDown, X } from 'lucide-react';
import * as React from 'react';

import { findZonesByQuery, zones, zonesBySlug } from '@inmobi/shared-types/zones';

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
  value: string | null;
  onChange: (slug: string | null) => void;
  placeholder?: string;
}

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

  const selected = value ? zonesBySlug.get(value) : null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal"
        >
          <span className={cn('truncate', !selected && 'text-muted-foreground')}>
            {selected ? selected.displayName : placeholder}
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
            {value && (
              <CommandGroup>
                <CommandItem
                  value="__clear__"
                  onSelect={() => {
                    onChange(null);
                    setOpen(false);
                    setQuery('');
                  }}
                  className="text-muted-foreground"
                >
                  <X className="mr-2 h-4 w-4" />
                  Quitar filtro
                </CommandItem>
              </CommandGroup>
            )}
            {groups.mdp.length > 0 && (
              <CommandGroup heading="Mar del Plata + barrios">
                {groups.mdp.map((z) => (
                  <CommandItem
                    key={z.slug}
                    value={z.slug}
                    onSelect={() => {
                      onChange(z.slug);
                      setOpen(false);
                      setQuery('');
                    }}
                  >
                    <Check
                      className={cn(
                        'mr-2 h-4 w-4',
                        value === z.slug ? 'opacity-100' : 'opacity-0',
                      )}
                    />
                    {z.displayName}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {groups.alrededores.length > 0 && (
              <CommandGroup heading="Alrededores">
                {groups.alrededores.map((z) => (
                  <CommandItem
                    key={z.slug}
                    value={z.slug}
                    onSelect={() => {
                      onChange(z.slug);
                      setOpen(false);
                      setQuery('');
                    }}
                  >
                    <Check
                      className={cn(
                        'mr-2 h-4 w-4',
                        value === z.slug ? 'opacity-100' : 'opacity-0',
                      )}
                    />
                    {z.displayName}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {groups.caba.length > 0 && (
              <CommandGroup heading="CABA">
                {groups.caba.map((z) => (
                  <CommandItem
                    key={z.slug}
                    value={z.slug}
                    onSelect={() => {
                      onChange(z.slug);
                      setOpen(false);
                      setQuery('');
                    }}
                  >
                    <Check
                      className={cn(
                        'mr-2 h-4 w-4',
                        value === z.slug ? 'opacity-100' : 'opacity-0',
                      )}
                    />
                    {z.displayName}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
