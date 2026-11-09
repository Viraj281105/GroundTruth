import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const incoming = new Map<string, string>();
vi.mock('next/headers', () => ({ headers: () => ({ get: (k: string) => incoming.get(k.toLowerCase()) ?? null }) }));

import { serverApi, serverApiBaseUrl } from '../src/lib/server-api';

const okFetch = () => vi.fn(async (_req: Request) => new Response(JSON.stringify({ organizations: [] }), { status: 200, headers: { 'content-type': 'application/json' } }));
const asFetch = (f: unknown) => f as typeof fetch;

describe('serverApi', () => {
  beforeEach(() => incoming.clear());
  afterEach(() => vi.unstubAllEnvs());

  it('forwards the incoming cookie header to the API', async () => {
    incoming.set('cookie', 'gt_session=abc123; theme=dark');
    vi.stubEnv('INTERNAL_API_URL', 'http://api.internal:9000');
    const f = okFetch();
    await serverApi({ fetch: asFetch(f) }).GET('/auth/me');
    const req = f.mock.calls[0][0];
    expect(req.headers.get('cookie')).toBe('gt_session=abc123; theme=dark');
    expect(req.url).toBe('http://api.internal:9000/auth/me');
  });

  it('sets the trusted Origin on unsafe calls even when the request had none', async () => {
    incoming.set('cookie', 'gt_session=abc');
    vi.stubEnv('SITE_URL', 'https://app.example.org/');
    const f = okFetch();
    await serverApi({ fetch: asFetch(f) }).POST('/orgs/active', { body: { slug: 'demo-ngo' } });
    const req = f.mock.calls[0][0];
    expect(req.method).toBe('POST');
    expect(req.headers.get('origin')).toBe('https://app.example.org');
  });

  it('never echoes an attacker-supplied Origin on unsafe calls', async () => {
    incoming.set('cookie', 'gt_session=abc');
    incoming.set('origin', 'https://evil.example');
    vi.stubEnv('SITE_URL', '');
    vi.stubEnv('NEXT_PUBLIC_SITE_URL', '');
    vi.stubEnv('FRONTEND_URL', '');
    const f = okFetch();
    await serverApi({ fetch: asFetch(f) }).POST('/orgs/active', { body: { slug: 'x' } });
    expect(f.mock.calls[0][0].headers.get('origin')).toBe('http://localhost:3000');
  });

  it('adds no Origin to safe calls', async () => {
    incoming.set('origin', 'https://evil.example');
    const f = okFetch();
    await serverApi({ fetch: asFetch(f) }).GET('/auth/me');
    expect(f.mock.calls[0][0].headers.has('origin')).toBe(false);
  });

  it('sends no cookie when the request has none', async () => {
    const f = okFetch();
    await serverApi({ fetch: asFetch(f) }).GET('/auth/me');
    expect(f.mock.calls[0][0].headers.has('cookie')).toBe(false);
  });

  it('replays a call once after making the page org active when the API answers 409 or 404', async () => {
    for (const status of [409, 404]) {
      incoming.clear();
      incoming.set('cookie', 'gt_session=abc');
      incoming.set('x-gt-path', '/app/demo-ngo/projects?x=1');
      let active = false;
      const f = vi.fn(async (req: Request) => {
        if (req.url.endsWith('/orgs/active')) {
          active = true;
          return new Response('{}', { status: 200 });
        }
        return active ? new Response('[]', { status: 200 }) : new Response('{}', { status });
      });
      const res = await serverApi({ fetch: asFetch(f) }).GET('/orgs/{slug}/projects', { params: { path: { slug: 'demo-ngo' } } });
      expect(res.response.status).toBe(200);
      const urls = f.mock.calls.map((c) => `${c[0].method} ${new URL(c[0].url).pathname}`);
      expect(urls).toEqual(['GET /orgs/demo-ngo/projects', 'POST /orgs/active', 'GET /orgs/demo-ngo/projects']);
      const post = f.mock.calls[1][0];
      expect(await post.json()).toEqual({ slug: 'demo-ngo' });
      expect(post.headers.get('cookie')).toBe('gt_session=abc');
      expect(post.headers.get('origin')).toBe('http://localhost:3000');
      expect(f.mock.calls[2][0].headers.get('x-gt-org-retry')).toBe('1');
    }
  });

  it('never replays or switches for an unsafe call that answers 409/404', async () => {
    incoming.set('x-gt-path', '/app/demo-ngo/projects');
    const f = vi.fn(async () => new Response('{}', { status: 409 }));
    const res = await serverApi({ fetch: asFetch(f) }).POST('/orgs/{slug}/members', { params: { path: { slug: 'demo-ngo' } }, body: { email: 'a@b.c', role: 'member' } as never });
    expect(res.response.status).toBe(409);
    expect(f).toHaveBeenCalledTimes(1);
  });

  it('switches once and replays once, never looping, when the replay also fails', async () => {
    incoming.set('x-gt-path', '/app/demo-ngo/projects');
    const f = vi.fn(async (req: Request) => new Response('{}', { status: req.url.endsWith('/orgs/active') ? 200 : 404 }));
    const api = serverApi({ fetch: asFetch(f) });
    const params = { params: { path: { slug: 'demo-ngo' } } };
    await api.GET('/orgs/{slug}/projects', params);
    await api.GET('/orgs/{slug}/projects', params);
    const posts = f.mock.calls.filter((c) => c[0].method === 'POST').length;
    expect(posts).toBe(1);
    expect(f.mock.calls.length).toBe(5); // 2 x (call + replay) + one switch
  });

  it('a malformed percent path yields no org and no replay', async () => {
    incoming.set('x-gt-path', '/app/%E0%A4%A/projects');
    const f = vi.fn(async () => new Response('{}', { status: 404 }));
    const res = await serverApi({ fetch: asFetch(f) }).GET('/orgs/{slug}/projects', { params: { path: { slug: 'x' } } });
    expect(res.response.status).toBe(404);
    expect(f).toHaveBeenCalledTimes(1);
  });

  it('does not switch or replay on pages that are not under /app/<org>', async () => {
    incoming.set('x-gt-path', '/status');
    const f = vi.fn(async () => new Response('{}', { status: 409 }));
    const res = await serverApi({ fetch: asFetch(f) }).GET('/orgs/{slug}/projects', { params: { path: { slug: 'x' } } });
    expect(res.response.status).toBe(409);
    expect(f).toHaveBeenCalledTimes(1);
  });

  it('prefers INTERNAL_API_URL, then the public base URL', () => {
    vi.stubEnv('INTERNAL_API_URL', 'http://internal:1');
    expect(serverApiBaseUrl()).toBe('http://internal:1');
    vi.stubEnv('INTERNAL_API_URL', '');
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://public:2');
    expect(serverApiBaseUrl()).toBe('http://public:2');
  });

  it('has no fixture fallback: a network failure rejects', async () => {
    incoming.set('cookie', 'gt_session=abc');
    const boom = vi.fn(async () => {
      throw new TypeError('fetch failed');
    });
    await expect(serverApi({ fetch: asFetch(boom) }).GET('/auth/me')).rejects.toThrow('fetch failed');
  });
});
