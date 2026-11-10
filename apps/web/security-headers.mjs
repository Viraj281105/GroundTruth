// Security headers for every page the web app serves (#51). Used by next.config.mjs.
//
// The Content-Security-Policy allows exactly what the app loads, and nothing else:
//   - its own scripts, styles, fonts and images ('self'; next/font self-hosts the fonts);
//   - the API origin (NEXT_PUBLIC_API_URL), which the browser calls directly;
//   - the OpenFreeMap basemap (style, tiles, glyphs, sprites) for the project maps;
//   - blob: workers, which MapLibre starts, and data:/blob: images.
//
// ACCEPTED, with the reason recorded in SECURITY.md: script-src allows 'unsafe-inline'. The
// Next.js App Router writes inline scripts to hydrate every page, and the layout sets the theme
// with one before first paint. The alternative, a per-request nonce, would force every page to
// render dynamically. Everything else (objects, framing, base URI, form targets) is locked down.
// 'unsafe-eval' and websocket connections are allowed in development only, for hot reload.

export const BASEMAP_ORIGIN = 'https://tiles.openfreemap.org';
const DEFAULT_API_URL = 'http://localhost:8000';

/** The origin of a URL, or null when it is not one. */
export function originOf(url) {
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

/**
 * @param {{ apiUrl?: string, isDev?: boolean }} [options]
 * @returns {string}
 */
export function contentSecurityPolicy({ apiUrl = DEFAULT_API_URL, isDev = false } = {}) {
  const api = originOf(apiUrl);
  const extra = (...sources) => sources.filter(Boolean);
  const directives = {
    'default-src': ["'self'"],
    'script-src': ["'self'", "'unsafe-inline'", ...extra(isDev && "'unsafe-eval'")],
    'style-src': ["'self'", "'unsafe-inline'"],
    'img-src': ["'self'", 'data:', 'blob:', BASEMAP_ORIGIN, ...extra(api)],
    'font-src': ["'self'", 'data:'],
    'connect-src': ["'self'", BASEMAP_ORIGIN, ...extra(api, isDev && 'ws:', isDev && 'wss:')],
    'worker-src': ["'self'", 'blob:'],
    'child-src': ["'self'", 'blob:'],
    'manifest-src': ["'self'"],
    'frame-src': ["'none'"],
    'object-src': ["'none'"],
    'base-uri': ["'self'"],
    'form-action': ["'self'"],
    'frame-ancestors': ["'none'"],
  };
  return Object.entries(directives)
    .map(([name, sources]) => `${name} ${[...new Set(sources)].join(' ')}`)
    .join('; ');
}

/**
 * Every security header, as Next.js `headers()` expects them.
 * @param {{ apiUrl?: string, isDev?: boolean, siteUrl?: string }} [options]
 * @returns {{ key: string, value: string }[]}
 */
export function securityHeaders({ apiUrl, isDev = false, siteUrl } = {}) {
  const headers = [
    { key: 'Content-Security-Policy', value: contentSecurityPolicy({ apiUrl, isDev }) },
    { key: 'X-Content-Type-Options', value: 'nosniff' },
    { key: 'X-Frame-Options', value: 'DENY' },
    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
    { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
    { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), payment=(), usb=()' },
  ];
  // HSTS only where the site is served over HTTPS: over plain HTTP it would do nothing at best.
  if (!isDev && typeof siteUrl === 'string' && siteUrl.startsWith('https://')) {
    headers.push({ key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' });
  }
  return headers;
}
