import { notFound } from 'next/navigation';
import { serverApi } from '../../lib/server-api';
import { loadMe } from '../../lib/server-session';
import type { Schemas } from '../../lib/api-client';

export type Fetched<T> = { data: T | null; status: number };

/** Runs one API call; a network failure is status 0 and never throws. */
export async function fetched<T>(call: () => Promise<{ data?: T; response: Response }>): Promise<Fetched<T>> {
  try {
    const r = await call();
    return { data: r.data ?? null, status: r.response.status };
  } catch {
    return { data: null, status: 0 };
  }
}

/** The project by slug or id. 404 (unknown or no access) becomes the framework's not-found page. */
export async function loadProject(idOrSlug: string): Promise<Schemas['ProjectView']> {
  const r = await fetched(() => serverApi().GET('/projects/{project_id}', { params: { path: { project_id: idOrSlug } } }));
  if (r.status === 404) notFound();
  if (!r.data) throw new Error(`The project could not be loaded (status ${r.status}).`);
  return r.data;
}

/** The caller's membership in the org named in the URL (the layout already proved it exists). */
export async function loadOrg(slug: string): Promise<Schemas['OrgView'] | null> {
  const me = await loadMe();
  if (me.status !== 'ok') return null;
  return me.me.organizations.find((o) => o.slug === slug) ?? null;
}

export async function loadMeUserId(): Promise<string | null> {
  const me = await loadMe();
  return me.status === 'ok' ? me.me.user?.id ?? null : null;
}
