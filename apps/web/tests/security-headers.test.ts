// Security headers for the web app (#51). The policy must allow what the pages load and refuse
// the rest; that every page still renders under it is checked by the e2e run (e2e/csp.spec.ts).
import { describe, expect, it } from 'vitest';

import { BASEMAP_ORIGIN, contentSecurityPolicy, originOf, securityHeaders } from '../security-headers.mjs';
import { BASEMAP_STYLE_URL } from '../src/components/map/geo';

function directives(csp: string): Map<string, string[]> {
  return new Map(
    csp.split(';').map((part) => {
      const [name, ...sources] = part.trim().split(/\s+/);
      return [name, sources];
    }),
  );
}

describe('content security policy', () => {
  const prod = directives(contentSecurityPolicy({ apiUrl: 'https://api.example.org/base/path' }));

  it('locks down framing, plugins, the base URI and form targets', () => {
    expect(prod.get('frame-ancestors')).toEqual(["'none'"]);
    expect(prod.get('object-src')).toEqual(["'none'"]);
    expect(prod.get('base-uri')).toEqual(["'self'"]);
    expect(prod.get('form-action')).toEqual(["'self'"]);
    expect(prod.get('default-src')).toEqual(["'self'"]);
  });

  it('lets the browser call the API by its origin only', () => {
    expect(prod.get('connect-src')).toContain('https://api.example.org');
    expect(prod.get('connect-src')?.some((s) => s.includes('/base/path'))).toBe(false);
  });

  it('allows the basemap the maps actually use, and the workers MapLibre starts', () => {
    expect(originOf(BASEMAP_STYLE_URL)).toBe(BASEMAP_ORIGIN);
    expect(prod.get('connect-src')).toContain(BASEMAP_ORIGIN);
    expect(prod.get('img-src')).toContain(BASEMAP_ORIGIN);
    expect(prod.get('worker-src')).toContain('blob:');
  });

  it("accepts inline scripts (Next.js hydration) but never eval in production", () => {
    expect(prod.get('script-src')).toContain("'unsafe-inline'");
    expect(prod.get('script-src')).not.toContain("'unsafe-eval'");
    expect(prod.get('connect-src')).not.toContain('ws:');
  });

  it('allows eval and websockets in development only, for hot reload', () => {
    const dev = directives(contentSecurityPolicy({ isDev: true }));
    expect(dev.get('script-src')).toContain("'unsafe-eval'");
    expect(dev.get('connect-src')).toContain('ws:');
  });

  it('falls back to the local API when NEXT_PUBLIC_API_URL is unset or not a URL', () => {
    expect(directives(contentSecurityPolicy()).get('connect-src')).toContain('http://localhost:8000');
    const broken = directives(contentSecurityPolicy({ apiUrl: 'not a url' }));
    expect(broken.get('connect-src')).toEqual(["'self'", BASEMAP_ORIGIN]);
  });

  it('never allows every origin', () => {
    expect(contentSecurityPolicy()).not.toMatch(/(^|\s)\*(\s|;|$)/);
  });
});

describe('security headers', () => {
  const names = (h: { key: string }[]) => h.map((x) => x.key);

  it('sends the full set on every page', () => {
    expect(names(securityHeaders())).toEqual([
      'Content-Security-Policy',
      'X-Content-Type-Options',
      'X-Frame-Options',
      'Referrer-Policy',
      'Cross-Origin-Opener-Policy',
      'Permissions-Policy',
    ]);
  });

  it('adds HSTS only for an HTTPS site outside development', () => {
    expect(names(securityHeaders({ siteUrl: 'https://groundtruth.example.org' }))).toContain(
      'Strict-Transport-Security',
    );
    expect(names(securityHeaders({ siteUrl: 'http://localhost:3000' }))).not.toContain(
      'Strict-Transport-Security',
    );
    expect(names(securityHeaders({ siteUrl: 'https://x.org', isDev: true }))).not.toContain(
      'Strict-Transport-Security',
    );
  });
});
