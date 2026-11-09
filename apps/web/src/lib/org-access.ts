import type { Schemas } from './api-client';
import { safeAppNextPath } from '../features/auth/validate';

type Me = Schemas['MeResponse'];
type Org = Schemas['OrgView'];

export type OrgAccess =
  | { kind: 'signed-out' }
  | { kind: 'no-organization' }
  | { kind: 'not-found' }
  | { kind: 'ok'; org: Org; orgs: Org[]; needsSwitch: boolean };

/**
 * Decides what `/app/<slug>/...` should do for this session. Pure so it can be tested; the layout acts
 * on the answer. Not a member and unknown slug are the same answer (404), as on the API.
 */
export function resolveOrgAccess(me: Me | null, slug: string): OrgAccess {
  if (!me || !me.user) return { kind: 'signed-out' };
  const orgs = me.organizations;
  if (orgs.length === 0) return { kind: 'no-organization' };
  const org = orgs.find((o) => o.slug === slug);
  if (!org) return { kind: 'not-found' };
  return { kind: 'ok', org, orgs, needsSwitch: me.active_organization?.slug !== slug };
}

/** Where `/app` should send a signed-in user: the active org's dashboard, else the first org's. */
export function landingPathFor(me: Me | null): string {
  if (!me || !me.user) return '/login?next=%2Fapp';
  const org = me.active_organization ?? me.organizations[0];
  return org ? `/app/${org.slug}/dashboard` : '/app/no-organization';
}

/** Login URL that returns to the page the visitor asked for (from middleware's x-gt-path), else /app. */
export function loginUrlFor(pathHeader: string | null | undefined): string {
  return `/login?next=${encodeURIComponent(safeAppNextPath(pathHeader))}`;
}

export type SwitchOutcome = 'ok' | 'signed-out' | 'not-found' | 'error';

/** What a POST /orgs/active status means for the layout. Anything non-2xx other than 401/404 is an error. */
export function switchOutcome(status: number | null): SwitchOutcome {
  if (status === null) return 'error';
  if (status >= 200 && status < 300) return 'ok';
  if (status === 401) return 'signed-out';
  if (status === 404) return 'not-found';
  return 'error';
}
