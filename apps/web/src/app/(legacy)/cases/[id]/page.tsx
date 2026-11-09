import React from 'react';
import { getRefusalFixture, getVisualizationFixture } from '../../../../lib/api';
import { loadCase } from '../../../../features/case/layout/load';
import { buildOverviewModel } from '../../../../features/case/overview/model';
import { OverviewView } from '../../../../features/case/overview/OverviewView';

export const metadata = { title: 'Case overview' };

export default async function CaseOverviewPage({ params }: { params: { id: string } }) {
  const load = await loadCase(params.id);
  // The layout already shows the not-found / unreachable state.
  if (load.status !== 'ok') return null;
  // Fixtures are non-null only when NEXT_PUBLIC_DEMO_MODE is explicitly on.
  // A completed fixture is the headline; the refusal demo only stands in when there is none.
  const fixture = getVisualizationFixture(params.id);
  const model = buildOverviewModel(load.detail, fixture, fixture ? null : getRefusalFixture(params.id));
  return <OverviewView caseId={params.id} model={model} />;
}
