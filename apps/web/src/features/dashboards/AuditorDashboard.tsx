import React from 'react';
import { LinkButton } from '../../components/ds';
import { SetDataMode } from '../../components/shell/data-mode';
import { AssessmentSummary } from '../../components/panels/AssessmentSummary';
import { EvidenceInventoryTable } from '../../components/panels/EvidenceInventoryTable';
import { ReadinessChecklist } from '../../components/panels/ReadinessChecklist';
import { VerdictPanel } from '../../components/panels/VerdictPanel';
import { ActivityFeed } from '../../components/panels/ActivityFeed';
import { getPublicApiUrl } from '../../lib/api';
import { dataModeFor, dataQuality } from './derive';
import type { DashboardData } from './loadDashboardData';
import { LibraryNotice, NoProjects, ProjectSwitcher, Question, Region, Slot } from './parts';
import styles from './dashboards.module.css';

export const AUDITOR_QUESTION = 'Which claims are substantiated and what evidence is missing?';

export function AuditorDashboard({ data }: { data: DashboardData }) {
  if (data.kind !== 'auditor') return null;
  const sel = data.scope?.selected ?? null;
  const live = sel && !data.scope?.libraryCase ? sel : null;
  const ok = <T,>(p: { status: 'ok'; data: T } | { status: 'unavailable' } | null): T | null => (p && p.status === 'ok' ? p.data : null);
  const dq = live ? dataQuality(ok(data.observations), ok(data.climate), ok(data.inventory)) : null;
  return (
    <div className={styles.dashboard} data-dashboard="auditor">
      <SetDataMode mode={sel ? dataModeFor([sel]) : 'observed'} />
      <Question text={AUDITOR_QUESTION} />
      <Slot panel={data.projects} title="Projects" render={(projects) => (projects.length === 0 || !data.scope ? <NoProjects orgSlug={data.orgSlug} readOnly /> : <ProjectSwitcher orgSlug={data.orgSlug} scope={data.scope} />)} />
      {sel && data.scope?.libraryCase && <LibraryNotice project={sel} />}
      {live && (
        <>
          <Region id="assessment" title={live.name} wide>
            <Slot panel={data.assessment} title="Assessment" render={(a) => <AssessmentSummary data={a} persona="auditor" />} />
          </Region>
          <div className={styles.grid}>
            <Region id="evidence-inventory" title="Evidence inventory" collapsible badge="Indicators & files">
              <Slot panel={data.inventory} title="Evidence inventory" render={(inv) => <EvidenceInventoryTable data={inv} level={live.access_level} />} />
            </Region>
            <Region id="verdict" title="Attribution, methodology and limitations" collapsible badge="Screening outcome">
              <Slot panel={data.verification} title="Verification" render={(v) => <VerdictPanel data={v} />} />
            </Region>
            <Region id="readiness" title="Attribution readiness" collapsible badge="Criteria checklist">
              <Slot panel={data.readiness} title="Readiness" render={(r) => <ReadinessChecklist data={r} />} />
            </Region>
            <Region id="data-quality" title="Data quality" collapsible badge="Coverage & sensors">
              {dq && (
                <ul className={styles.facts}>
                  <li>
                    AOI coverage (NDVI):{' '}
                    {dq.coverage ? (dq.coverage.min === dq.coverage.max ? `${dq.coverage.min.toFixed(1)}% across served years` : `${dq.coverage.min.toFixed(1)}% to ${dq.coverage.max.toFixed(1)}% across served years`) : 'not available'}
                  </li>
                  <li>Missing climate months: {dq.missingClimateMonths === null ? 'not available' : dq.missingClimateMonths}</li>
                  <li>Sensors: {dq.sensors.length ? dq.sensors.join(', ') : 'none reported'}</li>
                </ul>
              )}
            </Region>
            {(live.access_level === 'audit' || live.access_level === 'owner') && (
              <Region id="dossier" title="Audit dossier" collapsible defaultOpen badge="Accredited review">
                <p className={styles.muted}>The dossier bundles the evidence, hashes and methodology for accredited review.</p>
                <LinkButton variant="secondary" href={`${getPublicApiUrl()}/projects/${encodeURIComponent(live.id)}/export/dossier`} data-dossier-link>
                  Export audit dossier
                </LinkButton>
              </Region>
            )}
          </div>
        </>
      )}
      <Region id="activity" label="Recent activity" collapsible badge="Audit trail">
        <Slot panel={data.activity} title="Recent activity" render={(items) => <ActivityFeed items={items} />} />
      </Region>
    </div>
  );
}
