import { NextResponse, type NextRequest } from 'next/server';

export const SESSION_COOKIE = 'gt_session';
/** Request header carrying the path + query to server layouts, which cannot read the URL themselves. */
export const PATH_HEADER = 'x-gt-path';

/**
 * Edge gate for the org-scoped app: no session cookie means no page. This checks cookie presence
 * only; whether the session is valid and what it may see is always decided by the API.
 */
export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (request.cookies.has(SESSION_COOKIE)) {
    const forwarded = new Headers(request.headers);
    forwarded.set(PATH_HEADER, pathname + search);
    return NextResponse.next({ request: { headers: forwarded } });
  }
  const url = request.nextUrl.clone();
  url.pathname = '/login';
  url.search = `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(url);
}

export const config = { matcher: ['/app/:path*'] };
