import React from 'react';
import { notFound } from 'next/navigation';
import { UnavailablePanel } from '../../../../../components/ds/UnavailablePanel';
import { resolveOrgAccess } from '../../../../../lib/org-access';
import { loadMe } from '../../../../../lib/server-session';
import { dashboardFor } from '../../../../../features/dashboards/dashboardFor';
import { loadDashboardData } from '../../../../../features/dashboards/loadDashboardData';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Dashboard' };

/** The role-specific dashboard for the organization in the URL (the org layout has already authorized it). */
export default async function DashboardPage({ params, searchParams }: { params: { org: string }; searchParams?: { project?: string | string[] } }) {
  const load = await loadMe();
  const access = resolveOrgAccess(load.status === 'ok' ? load.me : null, params.org);
  if (access.kind === 'not-found') notFound();
  if (access.kind !== 'ok') {
    return <UnavailablePanel title="Dashboard" reason="The organization could not be resolved." evidenceNeeded="A reachable API and a signed-in session." />;
  }
  const project = Array.isArray(searchParams?.project) ? searchParams?.project[0] : searchParams?.project;
  const data = await loadDashboardData(params.org, access.org.type, { project });
  const Dashboard = dashboardFor(access.org.type);
  return <Dashboard data={data} />;
}
