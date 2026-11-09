import React from 'react';
import { EvidenceLibraryView } from '../../../../../components/panels/EvidenceLibraryView';
import type { ProjectDocsRow } from '../../../../../components/panels/evidenceLibrary.model';
import { fetched } from '../../../../../features/projects/server';
import { apiErrorMessage } from '../../../../../features/projects/model';
import { serverApi } from '../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Evidence Library & Dataset Registry — GroundTruth 2.0' };

/**
 * The registry is public static metadata, read from the API with the typed client. If it cannot be read the
 * page says so: there is no built-in list of datasets to fall back to.
 */
export default async function EvidenceLibraryPage({ params }: { params: { org: string } }) {
  const [registry, list] = await Promise.all([
    fetched(() => serverApi().GET('/evidence-registry', {})),
    fetched(() => serverApi().GET('/orgs/{slug}/projects', { params: { path: { slug: params.org } } })),
  ]);

  let projects: ProjectDocsRow[] | null = null;
  if (list.data) {
    projects = await Promise.all(
      list.data.map(async (p) => {
        const inv = await fetched(() => serverApi().GET('/projects/{project_id}/evidence-inventory', { params: { path: { project_id: p.id } } }));
        return { id: p.id, slug: p.slug, name: p.name, documentsCount: inv.data ? inv.data.documents_count : null };
      }),
    );
  }

  const error = registry.data ? null : `The dataset registry could not be loaded. ${apiErrorMessage(registry.status)}`;
  return <EvidenceLibraryView registry={registry.data} error={error} orgSlug={params.org} projects={projects} />;
}
