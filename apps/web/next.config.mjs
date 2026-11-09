/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
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
