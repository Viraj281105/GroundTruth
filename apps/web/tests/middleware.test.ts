import { describe, expect, it } from 'vitest';
import { NextRequest } from 'next/server';
import { config, middleware } from '../src/middleware';

const req = (path: string, cookie?: string) => new NextRequest(`http://localhost:3000${path}`, cookie ? { headers: { cookie } } : undefined);

describe('middleware', () => {
  it('redirects /app without a session cookie to /login with an encoded next', () => {
    const res = middleware(req('/app/demo-ngo/dashboard?tab=a&x=1'));
    expect(res.status).toBe(307);
    const loc = new URL(res.headers.get('location')!);
    expect(loc.pathname).toBe('/login');
    expect(loc.searchParams.get('next')).toBe('/app/demo-ngo/dashboard?tab=a&x=1');
    expect(loc.search).toBe(`?next=${encodeURIComponent('/app/demo-ngo/dashboard?tab=a&x=1')}`);
  });

  it('redirects bare /app too', () => {
    expect(new URL(middleware(req('/app')).headers.get('location')!).searchParams.get('next')).toBe('/app');
  });

  it('passes through with a gt_session cookie', () => {
    const res = middleware(req('/app/demo-ngo/dashboard', 'gt_session=abc'));
    expect(res.headers.get('location')).toBeNull();
    expect(res.headers.get('x-middleware-next')).toBe('1');
  });

  it('is not fooled by a similarly named cookie', () => {
    expect(middleware(req('/app', 'gt_session_old=1')).status).toBe(307);
  });

  it('hands the path and query to server layouts via x-gt-path', () => {
    const res = middleware(req('/app/demo-ngo/dashboard?tab=a', 'gt_session=abc'));
    expect(res.headers.get('x-middleware-request-x-gt-path')).toBe('/app/demo-ngo/dashboard?tab=a');
  });

  // Next 14 has no unstable_doesMiddlewareMatch helper, so only the declared matcher is asserted.
  it('is declared for /app paths only', () => {
    expect(config.matcher).toEqual(['/app/:path*']);
  });
});
