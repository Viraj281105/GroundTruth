import { headers } from 'next/headers';
import createClient from 'openapi-fetch';
import { getApiBaseUrl } from './api';
import type { paths } from './generated/schema';

/** Server-side API base: the internal address when set, otherwise the public resolution. */
export function serverApiBaseUrl(): string {
  return process.env.INTERNAL_API_URL || getApiBaseUrl();
}

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** The organization slug of the page being rendered (middleware's x-gt-path), if it is an /app/<org>/ page. */
function pageOrgSlug(path: string | null): string | null {
  const m = path ? /^\/app\/([^/?#]+)/.exec(path) : null;
  if (!m || m[1] === 'no-organization') return null;
  try {
    return decodeURIComponent(m[1]!);
  } catch {
    return null;
  }
}

/**
 * The origin the API's CSRF check expects for state-changing calls: the site's own public URL, which
 * must equal the API's FRONTEND_URL / one of its CORS_ALLOWED_ORIGINS. Trusted server config only.
 */
export function trustedSiteOrigin(): string {
  const raw = process.env.SITE_URL || process.env.NEXT_PUBLIC_SITE_URL || process.env.FRONTEND_URL || 'http://localhost:3000';
  return raw.replace(/\/+$/, '');
}

/**
 * A typed API client for server components. It forwards the incoming request's `cookie` header (the
 * HttpOnly `gt_session`). A server-side GET navigation carries no Origin, so for unsafe methods the
 * client sets `Origin` from trusted config (`trustedSiteOrigin`); it never echoes a request-supplied
 * Origin. Authorization is the API's decision. It never falls back to fixtures.
 */
export function serverApi(options: { fetch?: typeof globalThis.fetch } = {}) {
  const h = headers();
  const forwarded: Record<string, string> = {};
  const cookie = h.get('cookie');
  if (cookie) forwarded.cookie = cookie;
  const inner = options.fetch ?? ((...a: Parameters<typeof fetch>) => globalThis.fetch(...a));
  const origin = trustedSiteOrigin();
  const orgSlug = pageOrgSlug(h.get('x-gt-path'));
  let switched: Promise<void> | null = null;
  /**
   * Next renders a layout and its page concurrently, so a page's first call can reach the API before the
   * layout has made the URL's organization the session's active one. The API then answers 409
   * (no_active_organization) or 404 (another organization is active). Make the URL's organization active
   * (idempotent; the API still answers 404 for a non-member) and replay the call once.
   */
  const activateOrg = () =>
    (switched ??= inner(
      new Request(`${serverApiBaseUrl()}/orgs/active`, {
        method: 'POST',
        headers: { ...forwarded, origin, 'content-type': 'application/json' },
        body: JSON.stringify({ slug: orgSlug }),
        cache: 'no-store',
      }),
    ).then(() => undefined));
  return createClient<paths>({
    baseUrl: serverApiBaseUrl(),
    headers: forwarded,
    cache: 'no-store',
    fetch: async (req: Request) => {
      if (UNSAFE.has(req.method.toUpperCase())) req.headers.set('origin', origin);
      // Only safe methods are replayed: a legitimate 409/404 on a write must never switch orgs or double-submit.
      const retry = orgSlug && !UNSAFE.has(req.method.toUpperCase()) && !req.url.endsWith('/orgs/active') ? req.clone() : null;
      const res = await inner(req);
      if (retry && (res.status === 409 || res.status === 404)) {
        await activateOrg();
        // Next memoizes identical GETs within one render, which would replay the 409; a header makes it distinct.
        retry.headers.set('x-gt-org-retry', '1');
        return inner(retry);
      }
      return res;
    },
  });
}
