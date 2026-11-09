import React from 'react';
import { redirect } from 'next/navigation';
import { PortfolioTable } from '../../../../../components/panels/PortfolioTable';
import { SetDataMode } from '../../../../../components/shell/data-mode';
import { portfolioRedirect } from '../../../../../features/projects/model';
import { ProblemPanel } from '../../../../../features/projects/ProblemPanel';
import { fetched, loadOrg } from '../../../../../features/projects/server';
import { serverApi } from '../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Portfolio' };

/** Funders and governments only. Simulated projects are listed apart by the API; nothing is aggregated. */
export default async function PortfolioPage({ params }: { params: { org: string } }) {
  const org = await loadOrg(params.org);
  const to = org ? portfolioRedirect(params.org, org.type) : `/app/${params.org}/dashboard`;
  if (to) redirect(to);
  const r = await fetched(() => serverApi().GET('/orgs/{slug}/portfolio', { params: { path: { slug: params.org } } }));
  return (
    <>
      {r.data && r.data.simulated.length > 0 && <SetDataMode mode="simulated" />}
      <h1 style={{ fontSize: 'var(--text-3xl)', margin: '0 0 var(--space-5)' }}>Portfolio</h1>
      {r.data ? <PortfolioTable data={r.data} /> : <ProblemPanel title="Portfolio" status={r.status} />}
    </>
  );
}
