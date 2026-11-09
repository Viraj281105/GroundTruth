import React from 'react';
import { headers } from 'next/headers';
import { notFound, redirect } from 'next/navigation';
import { OrgShell } from '../../../../components/shell/OrgShell';
import { UnavailablePanel } from '../../../../components/ds/UnavailablePanel';
import { loginUrlFor, resolveOrgAccess, switchOutcome } from '../../../../lib/org-access';
import { serverApi } from '../../../../lib/server-api';
import { PATH_HEADER } from '../../../../middleware';
import { loadMe } from '../../../../lib/server-session';

export const dynamic = 'force-dynamic';

/** Every page under /app/<org> is rendered for one organization the caller belongs to. */
export default async function OrgLayout({ children, params }: { children: React.ReactNode; params: { org: string } }) {
  const load = await loadMe();
  if (load.status === 'unreachable') {
    return (
      <main className="gt-container" style={{ paddingBlock: 'var(--space-12)' }}>
        <UnavailablePanel title="Workspace" reason="The GroundTruth API could not be reached, so your organizations cannot be loaded." evidenceNeeded="A reachable API. Nothing is shown in its place." />
      </main>
    );
  }
  const access = resolveOrgAccess(load.status === 'ok' ? load.me : null, params.org);
  if (access.kind === 'signed-out') redirect(loginUrlFor(headers().get(PATH_HEADER)));
  if (access.kind === 'no-organization') redirect('/app/no-organization');
  if (access.kind === 'not-found') notFound();
  if (access.kind !== 'ok') notFound();

  if (access.needsSwitch) {
    // The API treats the active organization as session state; make it match the URL, then continue.
    let status: number | null = null;
    try {
      status = (await serverApi().POST('/orgs/active', { body: { slug: access.org.slug } })).response.status;
    } catch {
      status = null;
    }
    // redirect()/notFound() throw by design, so they stay outside the try block.
    const outcome = switchOutcome(status);
    if (outcome === 'signed-out') redirect(loginUrlFor(headers().get(PATH_HEADER)));
    if (outcome === 'not-found') notFound();
    if (outcome === 'error') {
      return (
        <main className="gt-container" style={{ paddingBlock: 'var(--space-12)' }}>
          <UnavailablePanel
            title="Workspace"
            reason={`Switching to this organization failed${status ? ` (API status ${status})` : ' (the API could not be reached)'}.`}
            evidenceNeeded="A successful organization switch from the API. Nothing is shown in its place."
          />
        </main>
      );
    }
  }
  return (
    <OrgShell orgs={access.orgs} active={access.org}>
      {children}
    </OrgShell>
  );
}
