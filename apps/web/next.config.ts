import path from 'node:path';

import type { NextConfig } from 'next';

const config: NextConfig = {
  reactStrictMode: true,
  // Silence the multi-lockfile warning — pin the monorepo as the workspace root.
  outputFileTracingRoot: path.resolve(process.cwd(), '../..'),
  transpilePackages: ['@inmobi/db', '@inmobi/shared-types'],
  serverExternalPackages: ['@prisma/client'],
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'http2.mlstatic.com' },
      { protocol: 'https', hostname: '*.mlstatic.com' },
      // Argenprop sirve las fotos desde su propio dominio; ZonaProp desde el CDN de
      // Navent (imgar.zonapropcdn.com / *.naventcdn.com). Sin esto, next/image no las
      // optimiza y caen sin lazy/resize (peor en mobile/datos móviles de MdP).
      { protocol: 'https', hostname: 'www.argenprop.com' },
      { protocol: 'https', hostname: 'imgar.zonapropcdn.com' },
      { protocol: 'https', hostname: '*.zonapropcdn.com' },
      { protocol: 'https', hostname: '*.naventcdn.com' },
    ],
  },
};

export default config;
