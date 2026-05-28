/** Formatters for prices, areas, etc. UI is in Spanish (es-AR). */

const usdFmt = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

const arsFmt = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  maximumFractionDigits: 0,
});

const intFmt = new Intl.NumberFormat('es-AR');

export function formatPrice(amount: number | string, currency: 'USD' | 'ARS'): string {
  const n = typeof amount === 'string' ? Number(amount) : amount;
  if (!Number.isFinite(n)) return '—';
  return currency === 'USD' ? usdFmt.format(n) : arsFmt.format(n);
}

export function formatSqm(value: number | string | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  const n = typeof value === 'string' ? Number(value) : value;
  if (!Number.isFinite(n)) return null;
  return `${intFmt.format(Math.round(n))} m²`;
}

export function pluralizeAmbientes(n: number): string {
  return n === 1 ? '1 ambiente' : `${n} ambientes`;
}

export function pluralizeBaños(n: number): string {
  return n === 1 ? '1 baño' : `${n} baños`;
}

export function formatRelativeDate(iso: string | Date): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  const diffMs = Date.now() - d.getTime();
  const diffH = Math.floor(diffMs / (1000 * 60 * 60));
  if (diffH < 1) return 'hace minutos';
  if (diffH < 24) return `hace ${diffH}h`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `hace ${diffD}d`;
  if (diffD < 30) return `hace ${Math.floor(diffD / 7)} sem`;
  return d.toLocaleDateString('es-AR');
}
