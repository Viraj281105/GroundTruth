import React from 'react';
import { ProblemPanel } from '../../../../../../features/projects/ProblemPanel';
import { fetched, loadMeUserId } from '../../../../../../features/projects/server';
import { requireSettingsAccess } from '../../../../../../features/settings/guard';
import { MembersTable } from '../../../../../../features/settings/MembersTable';
import { serverApi } from '../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Members' };

export default async function MembersPage({ params }: { params: { org: string } }) {
  const org = await requireSettingsAccess(params.org);
  const [members, userId] = await Promise.all([
    fetched(() => serverApi().GET('/orgs/{slug}/members', { params: { path: { slug: params.org } } })),
    loadMeUserId(),
  ]);
  return (
    <>
      <h1 style={{ fontSize: 'var(--text-3xl)', margin: '0 0 var(--space-2)' }}>Members</h1>
      <p style={{ color: 'var(--text-secondary)', margin: '0 0 var(--space-5)' }}>People in this organization and their roles. Only an existing GroundTruth account can be added.</p>
      {members.data ? <MembersTable orgSlug={params.org} actorRole={org.role} actorUserId={userId} initialMembers={members.data} /> : <ProblemPanel title="Members" status={members.status} />}
    </>
  );
}
