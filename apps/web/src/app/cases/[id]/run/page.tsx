import React from 'react';
import { RunFlow } from '../../../../features/run/RunFlow';

export const metadata = { title: 'Run an analysis' };

export default function Page({ params }: { params: { id: string } }) {
  return <RunFlow caseId={params.id} />;
}
