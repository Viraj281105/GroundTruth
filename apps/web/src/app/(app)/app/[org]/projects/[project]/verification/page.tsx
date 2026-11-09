import React from 'react';
import { Card } from '../../../../../../../components/ds';
import { UnavailablePanel } from '../../../../../../../components/ds/UnavailablePanel';
import { ReadinessChecklist } from '../../../../../../../components/panels/ReadinessChecklist';
import { VerdictPanel } from '../../../../../../../components/panels/VerdictPanel';
import { DiagnosticsSummary } from '../../../../../../../features/projects/DiagnosticsSummary';
import { diagnosticsVisible } from '../../../../../../../features/projects/model';
import { ProblemPanel } from '../../../../../../../features/projects/ProblemPanel';
import { fetched, loadProject } from '../../../../../../../features/projects/server';
import { ClaimVerificationWorkbench } from '../../../../../../../components/panels/ClaimVerificationWorkbench';
import { claimsProblem, toPortfolio } from '../../../../../../../components/panels/claimWorkbenchModel';
import styles from '../../../../../../../features/projects/projects.module.css';
import { serverApi } from '../../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Claim Verification Workbench — GroundTruth 2.0' };

export default async function VerificationPage({ params }: { params: { org: string; project: string } }) {
  const project = await loadProject(params.project);
  const path = { project_id: project.id };

  const [claimsRes, verification, assessment] = await Promise.all([
    fetched(() => serverApi().GET('/claims/structured/{project_id}', { params: { path } })),
    fetched(() => serverApi().GET('/projects/{project_id}/verification', { params: { path } })),
    fetched(() => serverApi().GET('/projects/{project_id}/assessment', { params: { path } })),
  ]);

  const v = verification.data;
  const a = assessment.data?.attribution;

  return (
    <>
      {claimsRes.data ? (
        <ClaimVerificationWorkbench
          projectName={project.name}
          orgSlug={params.org}
          projectSlug={project.slug}
          portfolio={toPortfolio(claimsRes.data)}
        />
      ) : (
        <UnavailablePanel
          title="Claim verification"
          reason={claimsProblem(claimsRes.status)}
          evidenceNeeded="A reachable API and access to this project. No substitute claims are shown."
        />
      )}

      {!v ? (
        <ProblemPanel title="Verification verdict" status={verification.status} />
      ) : (
        <>
          <VerdictPanel data={v} />
          {v.status === 'not_estimable' && <ReadinessChecklist data={v.readiness} />}
          {a && (
            <Card aria-label="Attribution">
              <h3 style={{ margin: '0 0 var(--space-2)' }}>Attribution</h3>
              <p>
                <b>{a.verdict}</b>. {a.finding}
              </p>
              <p className={styles.muted}>Methodology: {a.methodology}</p>
              <p className={styles.muted}>Limitation: {a.limitation}</p>
              {a.evidence_needed && <p className={styles.muted}>Evidence needed: {a.evidence_needed}</p>}
            </Card>
          )}
          {v.status === 'completed' && diagnosticsVisible(v.bundle, v.access_level) && <DiagnosticsSummary bundle={v.bundle} />}
        </>
      )}
    </>
  );
}
