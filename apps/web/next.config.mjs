import { securityHeaders } from './security-headers.mjs';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Security headers on every page (#51); what the CSP allows and why: security-headers.mjs.
  async headers() {
    return [
      {
        source: '/:path*',
        headers: securityHeaders({
          apiUrl: process.env.NEXT_PUBLIC_API_URL,
          isDev: process.env.NODE_ENV !== 'production',
          siteUrl: process.env.NEXT_PUBLIC_SITE_URL ?? process.env.SITE_URL,
        }),
      },
    ];
  },
  async redirects() {
    return [
      { source: '/health', destination: '/status', permanent: true },
      // The pre-2.0 case pages now live inside the org-scoped app. Kariba is owned by the Reference org.
      { source: '/cases', destination: '/app', permanent: false },
      { source: '/cases/new', destination: '/app', permanent: false },
      { source: '/cases/:id', destination: '/app/reference/projects/:id', permanent: false },
      { source: '/cases/:id/:path*', destination: '/app/reference/projects/:id/:path*', permanent: false },
    ];
  },
};

export default nextConfig;
