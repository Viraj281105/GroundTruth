import React from 'react';
import { redirect } from 'next/navigation';
import { UnavailablePanel } from '../../../components/ds/UnavailablePanel';
import { landingPathFor } from '../../../lib/org-access';
import { loadMe } from '../../../lib/server-session';

export const dynamic = 'force-dynamic';

/** /app sends the signed-in user to the active organization's dashboard, or to the "no organization" page. */
export default async function AppIndex() {
  const load = await loadMe();
  if (load.status === 'unreachable') {
    return (
      <main className="gt-container" style={{ paddingBlock: 'var(--space-12)' }}>
        <UnavailablePanel title="Workspace" reason="The GroundTruth API could not be reached, so your organizations cannot be loaded." evidenceNeeded="A reachable API. Nothing is shown in its place." />
      </main>
    );
  }
  redirect(landingPathFor(load.status === 'ok' ? load.me : null));
}
