import React from 'react';
import { getVisualizationFixture } from '../../../../lib/api';
import { loadCase } from '../../../../features/case/layout/load';
import { buildMethodModel } from '../../../../features/case/method/model';
import { MethodView } from '../../../../features/case/method/MethodView';

export const metadata = { title: 'Case method' };

export default async function CaseMethodPage({ params }: { params: { id: string } }) {
  const load = await loadCase(params.id);
  if (load.status !== 'ok') return null;
  const run = getVisualizationFixture(params.id)?.verification ?? null;
  const model = buildMethodModel(load.detail, run?.bundle.items ?? null, run?.bundle.verdict?.caveats ?? []);
  return <MethodView model={model} runId={run?.run_id ?? null} specHash={run?.spec_hash ?? null} />;
}
