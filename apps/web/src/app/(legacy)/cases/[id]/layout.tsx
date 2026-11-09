import React from 'react';
import { CaseHeader } from '../../../../features/case/layout/CaseHeader';
import { CaseNotFound, CaseUnreachable } from '../../../../features/case/layout/CaseStates';
import { loadCase } from '../../../../features/case/layout/load';

export default async function CaseLayout({ children, params }: { children: React.ReactNode; params: { id: string } }) {
  const load = await loadCase(params.id);
  if (load.status === 'not_found') return <CaseNotFound />;
  if (load.status === 'unreachable') return <CaseUnreachable apiBaseUrl={load.apiBaseUrl} />;
  return (
    <>
      <CaseHeader detail={load.detail} isDemo={load.isDemo} />
      {children}
    </>
  );
}
