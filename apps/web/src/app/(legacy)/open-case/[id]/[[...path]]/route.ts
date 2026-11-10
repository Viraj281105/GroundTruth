import { legacyCaseDestination } from '../../../../../lib/legacy-case-redirect';
import { loadMe } from '../../../../../lib/server-session';

export const dynamic = 'force-dynamic';

/**
 * Target of the `/cases/<id>[/<page>]` redirects in next.config.mjs. It needs the visitor's
 * session to choose the organization, which a static redirect cannot know.
 */
export async function GET(_request: Request, { params }: { params: { id: string; path?: string[] } }) {
  const load = await loadMe();
  // If the API cannot be reached, /app explains that instead of guessing an organization.
  const destination = load.status === 'unreachable' ? '/app' : legacyCaseDestination(load.status === 'ok' ? load.me : null, params.id, params.path?.[0]);
  // A relative Location keeps the visitor on the host they used (the server's own idea of its
  // origin is wrong behind a port mapping or a proxy).
  return new Response(null, { status: 307, headers: { Location: destination } });
}
