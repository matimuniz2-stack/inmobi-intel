'use client';

import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';

import L from 'leaflet';
import 'leaflet.markercluster';
import * as React from 'react';

import { formatPrice, formatSqm } from '@/lib/format';

export interface MapPoint {
  id: string;
  lat: number;
  lng: number;
  url: string;
  title: string | null;
  portal: 'MERCADOLIBRE' | 'ARGENPROP' | 'ZONAPROP';
  operationType: 'SALE' | 'RENT' | 'TEMP_RENT';
  propertyType: 'APT' | 'HOUSE' | 'PH' | 'LOCAL' | 'TERRENO' | 'OTRO';
  priceAmount: string;
  priceCurrency: 'USD' | 'ARS';
  priceUsdNormalized: string | null;
  bedrooms: number | null;
  bathrooms: number | null;
  totalSqm: string | null;
  coveredSqm: string | null;
  neighborhood: string | null;
  city: string | null;
  addressFull: string | null;
  agencyName: string | null;
  photo: string | null;
}

// Centro por defecto: Mar del Plata (el grueso de la operación). Si hay puntos,
// igual encuadramos a los puntos.
const MDP_CENTER: L.LatLngTuple = [-38.0055, -57.5426];
const DEFAULT_ZOOM = 12;

const OP_LABEL: Record<MapPoint['operationType'], string> = {
  SALE: 'Venta',
  RENT: 'Alquiler',
  TEMP_RENT: 'Alq. temporal',
};

const TYPE_LABEL: Record<MapPoint['propertyType'], string> = {
  APT: 'Departamento',
  HOUSE: 'Casa',
  PH: 'PH',
  LOCAL: 'Local',
  TERRENO: 'Terreno',
  OTRO: 'Otro',
};

const PORTAL_LABEL: Record<MapPoint['portal'], string> = {
  MERCADOLIBRE: 'MercadoLibre',
  ARGENPROP: 'Argenprop',
  ZONAPROP: 'ZonaProp',
};

// Color del pin por operación (igual criterio que los badges de la lista).
const OP_COLOR: Record<MapPoint['operationType'], string> = {
  SALE: '#059669', // emerald-600
  RENT: '#2563eb', // blue-600
  TEMP_RENT: '#d97706', // amber-600
};

const iconCache = new Map<string, L.DivIcon>();

function pinIcon(color: string): L.DivIcon {
  const cached = iconCache.get(color);
  if (cached) return cached;
  const icon = L.divIcon({
    className: 'inmobi-pin',
    html: `<svg width="26" height="34" viewBox="0 0 26 34" xmlns="http://www.w3.org/2000/svg">
      <path d="M13 0C5.8 0 0 5.8 0 13c0 9 13 21 13 21s13-12 13-21C26 5.8 20.2 0 13 0z"
        fill="${color}" stroke="#ffffff" stroke-width="2"/>
      <circle cx="13" cy="13" r="4.5" fill="#ffffff"/>
    </svg>`,
    iconSize: [26, 34],
    iconAnchor: [13, 34],
    popupAnchor: [0, -30],
  });
  iconCache.set(color, icon);
  return icon;
}

function esc(s: string | null | undefined): string {
  if (!s) return '';
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function popupHtml(p: MapPoint): string {
  const location = [p.neighborhood, p.city].filter(Boolean).join(', ');
  const sqm = formatSqm(p.coveredSqm) ?? formatSqm(p.totalSqm);
  const price = formatPrice(p.priceAmount, p.priceCurrency);
  const usd =
    p.priceCurrency === 'ARS' && p.priceUsdNormalized
      ? `<span style="color:#64748b;font-size:11px;margin-left:6px">≈ ${esc(formatPrice(p.priceUsdNormalized, 'USD'))}</span>`
      : '';

  const specs: string[] = [];
  if (p.bedrooms !== null) specs.push(`${p.bedrooms} amb`);
  if (p.bathrooms !== null) specs.push(`${p.bathrooms} baño${p.bathrooms === 1 ? '' : 's'}`);
  if (sqm) specs.push(esc(sqm));

  const photo = p.photo
    ? `<img src="${esc(p.photo)}" alt="" loading="lazy"
         style="width:100%;height:120px;object-fit:cover;display:block" />`
    : `<div style="width:100%;height:80px;display:flex;align-items:center;justify-content:center;background:#f1f5f9;color:#94a3b8;font-size:12px">Sin foto</div>`;

  return `
    <div style="width:230px">
      ${photo}
      <div style="padding:8px 10px 10px">
        <div style="font-weight:600;font-size:15px">${esc(price)}${usd}</div>
        ${location ? `<div style="color:#64748b;font-size:12px;margin-top:2px">${esc(location)}</div>` : ''}
        <div style="color:#475569;font-size:12px;margin-top:4px">
          ${esc(OP_LABEL[p.operationType])} · ${esc(TYPE_LABEL[p.propertyType])}${specs.length ? ' · ' + specs.join(' · ') : ''}
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:6px">
          <span style="color:#94a3b8;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px">
            ${esc(p.agencyName ?? PORTAL_LABEL[p.portal])}
          </span>
          <a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer"
             style="font-size:12px;font-weight:500;color:#2563eb;text-decoration:none;white-space:nowrap">Ver aviso →</a>
        </div>
      </div>
    </div>`;
}

function signature(points: MapPoint[]): string {
  // Barata y suficiente para detectar "cambió el conjunto" sin comparar todo.
  return `${points.length}:${points[0]?.id ?? ''}:${points[points.length - 1]?.id ?? ''}`;
}

export default function LeafletMap({ points }: { points: MapPoint[] }) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const mapRef = React.useRef<L.Map | null>(null);
  const clusterRef = React.useRef<L.MarkerClusterGroup | null>(null);
  const lastSigRef = React.useRef<string>('');

  // Inicialización (una vez).
  React.useEffect(() => {
    if (mapRef.current || !containerRef.current) return;

    const map = L.map(containerRef.current, {
      center: MDP_CENTER,
      zoom: DEFAULT_ZOOM,
      scrollWheelZoom: true,
    });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap',
      maxZoom: 19,
    }).addTo(map);

    const cluster = L.markerClusterGroup({
      maxClusterRadius: 50,
      showCoverageOnHover: false,
      chunkedLoading: true,
    });
    map.addLayer(cluster);

    mapRef.current = map;
    clusterRef.current = cluster;

    return () => {
      map.remove();
      mapRef.current = null;
      clusterRef.current = null;
    };
  }, []);

  // Render de markers cuando cambian los puntos.
  React.useEffect(() => {
    const map = mapRef.current;
    const cluster = clusterRef.current;
    if (!map || !cluster) return;

    cluster.clearLayers();

    const markers = points.map((p) => {
      const marker = L.marker([p.lat, p.lng], {
        icon: pinIcon(OP_COLOR[p.operationType]),
      });
      marker.bindPopup(popupHtml(p), { maxWidth: 250, minWidth: 230, autoPan: false });
      // "A lo Google Maps": el popup con foto + info aparece al pasar el mouse.
      marker.on('mouseover', () => marker.openPopup());
      return marker;
    });
    cluster.addLayers(markers);

    // Encuadrar a los puntos sólo cuando el conjunto cambió (no en cada refetch),
    // para no resetear el paneo/zoom mientras el usuario explora el mapa.
    const sig = signature(points);
    if (points.length > 0 && sig !== lastSigRef.current) {
      const bounds = L.latLngBounds(points.map((p) => [p.lat, p.lng] as L.LatLngTuple));
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
    }
    lastSigRef.current = sig;
  }, [points]);

  return <div ref={containerRef} className="h-full w-full" />;
}
