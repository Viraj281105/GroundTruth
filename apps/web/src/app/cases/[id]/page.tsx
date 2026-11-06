import React from 'react';
import { getRefusalFixture, getVisualizationFixture } from '../../../lib/api';
import { loadCase } from '../../../features/case/layout/load';
import { buildOverviewModel } from '../../../features/case/overview/model';
import { OverviewView } from '../../../features/case/overview/OverviewView';

export const metadata = { title: 'Case overview' };

export default async function CaseOverviewPage({ params }: { params: { id: string } }) {
  const load = await loadCase(params.id);
  // The layout already shows the not-found / unreachable state.
  if (load.status !== 'ok') return null;
  // Fixtures are non-null only when NEXT_PUBLIC_DEMO_MODE is explicitly on.
  const model = buildOverviewModel(load.detail, getVisualizationFixture(params.id), getRefusalFixture(params.id));
  return <OverviewView caseId={params.id} model={model} />;
}
