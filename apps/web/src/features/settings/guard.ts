import { redirect } from 'next/navigation';
import { loadOrg } from '../projects/server';
import { settingsRedirect } from './model';

/** Settings pages are for owners and admins; anyone else goes to the dashboard. Returns the caller's org. */
export async function requireSettingsAccess(orgSlug: string) {
  const org = await loadOrg(orgSlug);
  const to = org ? settingsRedirect(orgSlug, org.role) : `/app/${orgSlug}/dashboard`;
  if (to) redirect(to);
  return org!;
}
