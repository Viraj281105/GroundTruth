import React from 'react';
import { UnavailablePanel } from '../../components/ds/UnavailablePanel';
import { SetDataMode } from '../../components/shell/data-mode';
import ProjectMap from '../../components/map/ProjectMap';
import { boundaryUrlFor, donorsUrlFor } from '../../components/map/geo';
import { AssessmentSummary } from '../../components/panels/AssessmentSummary';
import { IndexSeriesPanel } from '../../components/panels/IndexSeriesPanel';
import { ClimatePanel } from '../../components/panels/ClimatePanel';
import { ReadinessChecklist } from '../../components/panels/ReadinessChecklist';
import { ActivityFeed } from '../../components/panels/ActivityFeed';
import { dataModeFor } from './derive';
import type { DashboardData } from './loadDashboardData';
import { LibraryNotice, NoProjects, ProjectSwitcher, Question, Region, Slot } from './parts';
import styles from './dashboards.module.css';

export const NGO_QUESTION = 'Where should we intervene or inspect?';

/** NGO layout; also used (read-only) by `reference` orgs. */
export function NgoDashboard({ data }: { data: DashboardData }) {
  if (data.kind !== 'ngo') return null;
  const sel = data.scope?.selected ?? null;
  return (
    <div className={styles.dashboard} data-dashboard="ngo" data-read-only={data.readOnly ? 'true' : 'false'}>
      <SetDataMode mode={sel ? dataModeFor([sel]) : 'observed'} />
      <Question text={NGO_QUESTION} />
      {data.readOnly && <p className={styles.muted}>Reference library: this workspace is read-only.</p>}
      <Slot panel={data.projects} title="Projects" render={(projects) => (projects.length === 0 || !data.scope ? <NoProjects orgSlug={data.orgSlug} readOnly={data.readOnly} /> : <ProjectSwitcher orgSlug={data.orgSlug} scope={data.scope} />)} />
      {sel && data.scope?.libraryCase && <LibraryNotice project={sel} />}
      {sel && !data.scope?.libraryCase && (
        <>
          <Region id="assessment" title={sel.name} wide>
            <Slot panel={data.assessment} title="Assessment" render={(a) => <AssessmentSummary data={a} persona="ngo" />} />
          </Region>
          <div className={styles.grid}>
            <Region id="map" title="Project area and comparison areas">
              <ProjectMap boundaryUrl={boundaryUrlFor(sel.id)} donorsUrl={donorsUrlFor(sel.id)} />
            </Region>
            <Region id="index-series" title="Vegetation indices" collapsible defaultOpen badge="Observations">
              <Slot panel={data.series} title="Vegetation indices" render={(series) => <IndexSeriesPanel series={series} />} />
            </Region>
            <Region id="climate" title="Climate context" collapsible badge="Weather & drought">
              <Slot panel={data.climate} title="Climate" render={(c) => <ClimatePanel data={c} />} />
            </Region>
            <Region id="readiness" title="Attribution readiness" collapsible badge="Criteria checklist">
              <Slot panel={data.readiness} title="Readiness" render={(r) => <ReadinessChecklist data={r} />} />
            </Region>
            <Region id="field-tasks" title="Field tasks" collapsible badge="Operations">
              <UnavailablePanel title="Field tasks" reason="Available in a later release: requires the field-operations module." evidenceNeeded="The field-operations module (a later sub-project)." />
            </Region>
            <Region id="risk-alerts" title="Risk alerts" collapsible badge="Intelligence">
              <UnavailablePanel title="Risk alerts" reason="Available in a later release: requires the risk-intelligence module." evidenceNeeded="The risk-intelligence module (a later sub-project)." />
            </Region>
          </div>
        </>
      )}
      <Region id="activity" label="Recent activity" collapsible badge="Audit trail">
        <Slot panel={data.activity} title="Recent activity" render={(items) => <ActivityFeed items={items} />} />
      </Region>
    </div>
  );
}

