# apps/web

Frontend Next.js 15 (App Router) + tRPC v11 + Tailwind 3 + shadcn-style primitives.

## Estructura

```
app/
├── layout.tsx              (RootLayout con <Providers>)
├── page.tsx                (redirect a /buscar)
├── globals.css
├── buscar/page.tsx         (entrada de búsqueda reversa)
└── api/trpc/[trpc]/route.ts (handler tRPC)

components/
├── providers.tsx           (React Query + tRPC client)
├── ui/                     (button, input, label, popover, command, badge, skeleton)
└── search/
    ├── search-page.tsx     (página principal client component)
    ├── zone-combobox.tsx   (autocomplete con cmdk + 52 zonas)
    └── property-card.tsx   (card de resultado)

lib/
├── utils.ts                (cn helper)
├── format.ts               (formatters de precio, m², plurales)
└── trpc/
    ├── server.ts           (init tRPC + superjson transformer)
    ├── client.ts           (createTRPCReact<AppRouter>)
    └── routers/
        ├── _app.ts
        └── properties.ts   (search query con Prisma)
```

## Bootstrap

```bash
# Desde la raíz del monorepo
pnpm install
pnpm db:up           # asegura que Postgres local está arriba

# En apps/web/, el .env.local apunta a localhost:5433
pnpm --filter @inmobi/web dev
```

Después abrí http://localhost:3000 (redirige a `/buscar`).

## Filtros disponibles

- **Zona**: combobox con 52 zonas (MdP region + 48 barrios CABA), autocomplete con aliases.
- **Operación**: Venta / Alquiler / Alq. temporal (default: Venta).
- **Tipo de propiedad**: Departamento / Casa / PH / Local / Terreno / Otro.
- **Ambientes mínimo**: número entero.
- **Precio USD**: min / max (usa `price_usd_normalized` calculado en M3).

## Notas

- **tRPC**: usa `superjson` transformer porque las queries devuelven `Decimal` y `Date`.
- **Paginación**: offset-based, 24 por página. Para Fase 1 alcanza; cursor-based si crecemos.
- **Imágenes**: cargadas directo desde `http2.mlstatic.com` (configurado en `next.config.ts`). No usamos `<Image>` de Next por ahora — `<img>` simple para evitar config de domain/dimensions.
