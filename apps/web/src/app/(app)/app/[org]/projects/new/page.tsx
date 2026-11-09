import React from 'react';
import { redirect } from 'next/navigation';
import { canCreateProject } from '../../../../../../features/projects/model';
import { loadOrg } from '../../../../../../features/projects/server';
import { NewProjectForm } from '../../../../../../features/projects/NewProjectForm';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'New project' };

export default async function NewProjectPage({ params }: { params: { org: string } }) {
  const org = await loadOrg(params.org);
  if (!org || !canCreateProject(org.type, org.role)) redirect(`/app/${params.org}/projects`);
  return (
    <>
      <h1 style={{ fontSize: 'var(--text-3xl)', margin: '0 0 var(--space-2)' }}>New project</h1>
      <p style={{ color: 'var(--text-secondary)', margin: '0 0 var(--space-5)' }}>
        Upload the project boundary. GroundTruth reads the observations it has for that area; nothing is estimated until the readiness criteria are met.
      </p>
      <NewProjectForm orgSlug={params.org} />
    </>
  );
}
