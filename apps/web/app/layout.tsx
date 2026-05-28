import type { Metadata, Viewport } from 'next';

import { Providers } from '@/components/providers';

import './globals.css';

export const metadata: Metadata = {
  title: 'Inmobi Intel — Búsqueda Reversa',
  description:
    'Búsqueda reversa multi-portal para inmobiliaria Zamboni. Mar del Plata + CABA.',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-AR">
      <body className="min-h-dvh bg-background antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
