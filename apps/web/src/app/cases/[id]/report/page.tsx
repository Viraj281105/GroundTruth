import React from 'react';
import { getVisualizationFixture } from '../../../../lib/api';
import { loadCase } from '../../../../features/case/layout/load';
import { formatCitation } from '../../../../features/case/report/citation';
import { buildOverviewModel } from '../../../../features/case/overview/model';
import { ReportView } from '../../../../features/case/report/ReportView';

export const metadata = { title: 'Case report' };

export default async function CaseReportPage({ params }: { params: { id: string } }) {
  const load = await loadCase(params.id);
  if (load.status !== 'ok') return null;
  const fixture = getVisualizationFixture(params.id);
  const run = fixture?.verification ?? null;
  const report = run
    ? {
        markdown: run.report_markdown,
        generator: run.report_generator,
        overview: buildOverviewModel(load.detail, fixture, null),
        citation: formatCitation({
          caseName: load.detail.name,
          standard: load.detail.standard,
          registryId: load.detail.registry_id,
          runId: run.run_id,
          specHash: run.spec_hash,
          dataMode: run.data_mode,
          generator: run.report_generator,
        }),
      }
    : null;
  return <ReportView caseId={params.id} report={report} />;
}
