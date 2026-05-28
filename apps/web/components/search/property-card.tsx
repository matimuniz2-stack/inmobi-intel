'use client';

import { Bath, Bed, ExternalLink, MapPin, Maximize2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import {
  formatPrice,
  formatRelativeDate,
  formatSqm,
  pluralizeAmbientes,
  pluralizeBaños,
} from '@/lib/format';

interface PropertyLike {
  id: string;
  portalId: string;
  url: string;
  operationType: 'SALE' | 'RENT' | 'TEMP_RENT';
  propertyType: 'APT' | 'HOUSE' | 'PH' | 'LOCAL' | 'TERRENO' | 'OTRO';
  priceAmount: string | number;
  priceCurrency: 'USD' | 'ARS';
  priceUsdNormalized: string | number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  totalSqm: string | number | null;
  coveredSqm: string | number | null;
  addressFull: string | null;
  neighborhood: string | null;
  city: string | null;
  photos: unknown;
  agencyName: string | null;
  lastUpdatedAt: Date | string;
}

const OP_LABEL: Record<PropertyLike['operationType'], string> = {
  SALE: 'Venta',
  RENT: 'Alquiler',
  TEMP_RENT: 'Alq. temporal',
};

const TYPE_LABEL: Record<PropertyLike['propertyType'], string> = {
  APT: 'Departamento',
  HOUSE: 'Casa',
  PH: 'PH',
  LOCAL: 'Local',
  TERRENO: 'Terreno',
  OTRO: 'Otro',
};

function firstPhoto(photos: unknown): string | null {
  if (!Array.isArray(photos)) return null;
  const first = photos[0];
  return typeof first === 'string' ? first : null;
}

export function PropertyCard({ p }: { p: PropertyLike }) {
  const photo = firstPhoto(p.photos);
  const sqm = formatSqm(p.coveredSqm) ?? formatSqm(p.totalSqm);
  const location = [p.neighborhood, p.city].filter(Boolean).join(', ');

  return (
    <article className="group flex flex-col overflow-hidden rounded-lg border bg-card shadow-sm transition-shadow hover:shadow-md">
      <div className="relative aspect-[4/3] overflow-hidden bg-muted">
        {photo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={photo}
            alt={p.addressFull ?? location ?? 'Propiedad'}
            className="h-full w-full object-cover transition-transform group-hover:scale-[1.02]"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
            Sin foto
          </div>
        )}
        <div className="absolute left-2 top-2 flex gap-1">
          <Badge variant="secondary" className="bg-white/90 text-foreground">
            {OP_LABEL[p.operationType]}
          </Badge>
          <Badge variant="secondary" className="bg-white/90 text-foreground">
            {TYPE_LABEL[p.propertyType]}
          </Badge>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-baseline justify-between gap-2">
          <div className="text-lg font-semibold">
            {formatPrice(p.priceAmount, p.priceCurrency)}
          </div>
          {p.priceCurrency === 'ARS' && p.priceUsdNormalized && (
            <div className="text-xs text-muted-foreground">
              ≈ {formatPrice(p.priceUsdNormalized, 'USD')}
            </div>
          )}
        </div>

        {location && (
          <div className="flex items-start gap-1 text-sm text-muted-foreground">
            <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="line-clamp-1">{location}</span>
          </div>
        )}

        <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted-foreground">
          {p.bedrooms !== null && (
            <span className="inline-flex items-center gap-1">
              <Bed className="h-3.5 w-3.5" />
              {pluralizeAmbientes(p.bedrooms)}
            </span>
          )}
          {p.bathrooms !== null && (
            <span className="inline-flex items-center gap-1">
              <Bath className="h-3.5 w-3.5" />
              {pluralizeBaños(p.bathrooms)}
            </span>
          )}
          {sqm && (
            <span className="inline-flex items-center gap-1">
              <Maximize2 className="h-3.5 w-3.5" />
              {sqm}
            </span>
          )}
        </div>

        <div className="mt-auto flex items-center justify-between gap-2 pt-2 text-xs text-muted-foreground">
          <span className="line-clamp-1">{p.agencyName ?? 'Sin inmobiliaria'}</span>
          <span className="shrink-0">{formatRelativeDate(p.lastUpdatedAt)}</span>
        </div>

        <a
          href={p.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center justify-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent"
        >
          Ver aviso
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>
    </article>
  );
}
