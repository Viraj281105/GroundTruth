import React from 'react';
import { EmptyState } from '../../../../../../components/ds';
import { ProblemPanel } from '../../../../../../features/projects/ProblemPanel';
import { fetched } from '../../../../../../features/projects/server';
import { requireSettingsAccess } from '../../../../../../features/settings/guard';
import { SharingManager } from '../../../../../../features/settings/SharingManager';
import { serverApi } from '../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Sharing' };

/** Sharing applies to projects this organization owns; granted projects belong to someone else. */
export default async function SharingPage({ params }: { params: { org: string } }) {
  await requireSettingsAccess(params.org);
  const list = await fetched(() => serverApi().GET('/orgs/{slug}/projects', { params: { path: { slug: params.org } } }));
  if (!list.data) return <ProblemPanel title="Sharing" status={list.status} />;
  const owned = list.data.filter((p) => p.access_level === 'owner');
  const grants = await Promise.all(owned.map((p) => fetched(() => serverApi().GET('/projects/{project_id}/grants', { params: { path: { project_id: p.id } } }))));
  return (
    <>
      <h1 style={{ fontSize: 'var(--text-3xl)', margin: '0 0 var(--space-2)' }}>Sharing</h1>
      <p style={{ color: 'var(--text-secondary)', margin: '0 0 var(--space-5)' }}>
        Grant another organization view, audit or contribute access to a project you own. Revoking takes effect on their next request.
      </p>
      {owned.length === 0 ? (
        <EmptyState title="No owned projects" body="Projects this organization owns can be shared from here." />
      ) : (
        <div style={{ display: 'grid', gap: 'var(--space-6)' }}>
          {owned.map((p, i) =>
            grants[i]?.data ? (
              <SharingManager key={p.id} projectId={p.id} projectName={p.name} ownerSlug={p.owner_slug} initialGrants={grants[i]!.data!} />
            ) : (
              <ProblemPanel key={p.id} title={`Sharing for ${p.name}`} status={grants[i]?.status ?? 0} />
            ),
          )}
        </div>
      )}
    </>
  );
}
