'use client';

import { Bath, Bed, ExternalLink, Flame, MapPin, Maximize2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import {
  formatPrice,
  formatRelativeDate,
  formatSqm,
  pluralizeAmbientes,
  pluralizeBaños,
} from '@/lib/format';
import { cn } from '@/lib/utils';

interface PropertyLike {
  id: string;
  portal: 'MERCADOLIBRE' | 'ARGENPROP' | 'ZONAPROP';
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
  neighborhood: string | null;
  city: string | null;
  photos: unknown;
  agencyName: string | null;
  lastUpdatedAt: Date | string;
}

export interface OpportunityLike {
  id: string;
  score: number;
  reasons: string[];
  property: PropertyLike;
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

const PORTAL_LABEL: Record<PropertyLike['portal'], string> = {
  MERCADOLIBRE: 'MercadoLibre',
  ARGENPROP: 'Argenprop',
  ZONAPROP: 'ZonaProp',
};

const PORTAL_BADGE_CLASS: Record<PropertyLike['portal'], string> = {
  MERCADOLIBRE: 'bg-yellow-300 text-yellow-950 hover:bg-yellow-300 border-yellow-400',
  ARGENPROP: 'bg-emerald-500 text-white hover:bg-emerald-500 border-emerald-600',
  ZONAPROP: 'bg-red-600 text-white hover:bg-red-600 border-red-700',
};

// Color del score por tramo. Verde = oportunidad fuerte, ámbar = buena, gris = leve.
function scoreTier(score: number): { className: string; label: string } {
  if (score >= 60)
    return { className: 'bg-emerald-600 text-white border-emerald-700', label: 'Fuerte' };
  if (score >= 35)
    return { className: 'bg-amber-500 text-amber-950 border-amber-600', label: 'Buena' };
  return { className: 'bg-slate-600 text-white border-slate-700', label: 'Leve' };
}

function firstPhoto(photos: unknown): string | null {
  if (!Array.isArray(photos)) return null;
  const first = photos[0];
  return typeof first === 'string' ? first : null;
}

export function OpportunityCard({ o }: { o: OpportunityLike }) {
  const p = o.property;
  const photo = firstPhoto(p.photos);
  const sqm = formatSqm(p.coveredSqm) ?? formatSqm(p.totalSqm);
  const location = [p.neighborhood, p.city].filter(Boolean).join(', ');
  const tier = scoreTier(o.score);

  return (
    <article className="group flex flex-col overflow-hidden rounded-lg border bg-card shadow-sm transition-shadow hover:shadow-md">
      <div className="relative aspect-[4/3] overflow-hidden bg-muted">
        {photo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={photo}
            alt={location || 'Propiedad'}
            className="h-full w-full object-cover transition-transform group-hover:scale-[1.02]"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
            Sin foto
          </div>
        )}
        <div className="absolute left-2 top-2">
          <Badge
            className={cn('gap-1 px-2 py-1 text-sm font-bold shadow', tier.className)}
            title={`Score de oportunidad: ${o.score}/100`}
          >
            <Flame className="h-3.5 w-3.5" />
            {o.score}
          </Badge>
        </div>
        <div className="absolute right-2 top-2">
          <Badge className={PORTAL_BADGE_CLASS[p.portal] ?? ''}>
            {PORTAL_LABEL[p.portal] ?? p.portal}
          </Badge>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Badge variant="secondary">{OP_LABEL[p.operationType]}</Badge>
          <Badge variant="secondary">{TYPE_LABEL[p.propertyType]}</Badge>
        </div>

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

        {/* Razones: el corazón del producto — por qué esto es oportunidad. */}
        <div className="mt-1 rounded-md border border-emerald-200 bg-emerald-50 p-2.5">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-800">
            Por qué es oportunidad
          </p>
          <ul className="space-y-1">
            {o.reasons.map((reason, i) => (
              <li key={i} className="flex gap-1.5 text-sm leading-snug text-emerald-950">
                <span aria-hidden className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
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
