import React from 'react';
import { RunFlow } from '../../../../../features/run/RunFlow';
import { RequireAuth } from '../../../../../features/auth/RequireAuth';

export const metadata = { title: 'Run an analysis' };

export default function Page({ params }: { params: { id: string } }) {
  return (
    <RequireAuth action="run analyses">
      <RunFlow caseId={params.id} />
    </RequireAuth>
  );
}
