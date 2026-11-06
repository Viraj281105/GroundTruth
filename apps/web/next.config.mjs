/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async redirects() {
    return [{ source: '/health', destination: '/status', permanent: true }];
  },
};

export default nextConfig;
