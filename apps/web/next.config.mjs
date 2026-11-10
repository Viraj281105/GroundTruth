/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async redirects() {
    return [
      // Common alternate names for the auth pages. Next keeps the query string, so ?next=... survives.
      { source: '/sign-in', destination: '/login', permanent: false },
      { source: '/signin', destination: '/login', permanent: false },
      { source: '/sign-up', destination: '/register', permanent: false },
      { source: '/health', destination: '/status', permanent: true },
      // The pre-2.0 case pages now live inside the org-scoped app. A project opens under the visitor's
      // own organization (never a fixed one, which other organizations cannot open), so the last two
      // go to a route that reads the session: src/app/(legacy)/open-case/[id]/[[...path]]/route.ts.
      { source: '/cases', destination: '/app', permanent: false },
      { source: '/cases/new', destination: '/app', permanent: false },
      { source: '/cases/:id', destination: '/open-case/:id', permanent: false },
      { source: '/cases/:id/:path*', destination: '/open-case/:id/:path*', permanent: false },
    ];
  },
};

export default nextConfig;
