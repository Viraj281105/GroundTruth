import React from 'react';
import { UnavailablePanel } from '../../components/ds/UnavailablePanel';
import { SetDataMode } from '../../components/shell/data-mode';
import ProjectMap from '../../components/map/ProjectMap';
import { boundaryUrlFor } from '../../components/map/geo';
import { PortfolioTable } from '../../components/panels/PortfolioTable';
import { climateHeadline, dataModeFor, mappableProjects } from './derive';
import type { DashboardData } from './loadDashboardData';
import { Hint, Question, Region, Slot } from './parts';
import styles from './dashboards.module.css';

export const GOVERNMENT_QUESTION = 'Which landscapes need attention?';
export const GOVERNMENT_HELP = 'See where projects sit on the map, how each is rated, and how dry or wet recent years have been. Only real, observed projects are drawn on the map.';

export function GovernmentDashboard({ data }: { data: DashboardData }) {
  if (data.kind !== 'government') return null;
  const all = data.projects.status === 'ok' ? data.projects.data : [];
  // Simulated projects are never drawn with real ones; they appear only in the labelled simulated portfolio section.
  const bounded = mappableProjects(all);
  const regional = bounded.map((p) => boundaryUrlFor(p.id));
  const mode = dataModeFor([...all, ...(data.portfolio.status === 'ok' ? data.portfolio.data.simulated.map((r) => r.project) : [])]);
  return (
    <div className={styles.dashboard} data-dashboard="government">
      <SetDataMode mode={mode} />
      <Question text={GOVERNMENT_QUESTION} help={GOVERNMENT_HELP} />
      <Region id="map" title="Project footprints" wide>
        {data.projects.status === 'unavailable' ? (
          <UnavailablePanel title="Project footprints" reason={data.projects.reason} evidenceNeeded="A reachable API. No substitute map is shown." />
        ) : regional.length === 0 ? (
          <p className={styles.muted}>No accessible observed project has a boundary to draw.</p>
        ) : (
          <ProjectMap regionalBoundaries={regional} />
        )}
      </Region>
      <Region id="portfolio" label="Assessment levels across accessible projects" wide>
        <Slot panel={data.portfolio} title="Portfolio" render={(p) => <PortfolioTable data={p} />} />
      </Region>
      <div className={styles.grid}>
        <Region id="climate-headlines" title="Climate headline by project" collapsible badge="Observed projects">
          <p className={styles.muted}>Observed projects only. Values are for the latest year available. The drought label comes from the weather record (<Hint id="spi" />).</p>
          {data.climate.length === 0 && <p className={styles.muted}>No accessible observed project has climate data.</p>}
          <ul className={styles.headlines}>
            {data.climate.map((e) => {
              if (e.climate.status === 'unavailable') {
                return (
                  <li key={e.project.id} data-climate-project={e.project.slug}>
                    <UnavailablePanel title={`${e.project.name} climate`} reason={e.climate.reason} evidenceNeeded="A reachable API and climate data for this project." />
                  </li>
                );
              }
              const h = climateHeadline(e.climate.data);
              return (
                <li key={e.project.id} data-climate-project={e.project.slug}>
                  <strong>{e.project.name}</strong>:{' '}
                  {h ? `${h.year}: ${Math.round(h.annualRainfallMm)} mm annual rainfall, drought class "${h.drought}"` : 'no climate data served for this project'}
                </li>
              );
            })}
          </ul>
        </Region>
        <Region id="regional-spi" title="District climate and drought" collapsible badge="Regional summaries">
          <UnavailablePanel title="District climate summary" reason="Regional district climate summaries are not served by the API yet." evidenceNeeded="A regional climate endpoint (later sub-project)." />
        </Region>
      </div>
    </div>
  );
}
