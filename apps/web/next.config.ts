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
    ],
  },
};

export default config;
