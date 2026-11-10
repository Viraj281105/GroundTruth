import type { Schemas } from './api-client';

type Me = Schemas['MeResponse'];

/** Pre-2.0 case sub-pages and the project tab that now holds the same material. */
const TAB_FOR_LEGACY_PAGE: Record<string, string> = {
  evidence: 'evidence',
  report: 'reports',
  reports: 'reports',
  method: 'verification',
  robustness: 'verification',
  run: 'observation',
};

/**
 * Where an old `/cases/<id>[/<page>]` link should go for this visitor.
 *
 * A project is opened under the visitor's own organization, because that is the only place
 * their access to it is decided. The old redirect sent everyone to the Reference organization,
 * which every other organization's members cannot open, so the link ended in "not found".
 * Whether the visitor may see the project is still decided by the API when the page loads.
 */
export function legacyCaseDestination(me: Me | null, caseId: string, legacyPage?: string): string {
  // The sign-in page only returns to /app paths, so a signed-out visitor lands on their workspace.
  if (!me || !me.user) return '/login?next=%2Fapp';
  const org = me.active_organization ?? me.organizations[0];
  if (!org) return '/app/no-organization';
  const tab = (legacyPage && TAB_FOR_LEGACY_PAGE[legacyPage]) || 'overview';
  return `/app/${org.slug}/projects/${encodeURIComponent(caseId)}/${tab}`;
}
