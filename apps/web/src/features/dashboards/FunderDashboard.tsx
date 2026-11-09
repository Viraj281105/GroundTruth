import React from 'react';
import { SetDataMode } from '../../components/shell/data-mode';
import { PortfolioTable } from '../../components/panels/PortfolioTable';
import { ActivityFeed } from '../../components/panels/ActivityFeed';
import { dataModeFor, needsAttention } from './derive';
import type { DashboardData } from './loadDashboardData';
import { Question, Region, Slot } from './parts';
import styles from './dashboards.module.css';

export const FUNDER_QUESTION = 'Which projects show measurable progress or need investigation?';
export const FUNDER_HELP = 'Compare the projects you fund or have been shared with. Projects marked for review have evidence gaps or results worth a closer look; that is a prompt to ask questions, not a finding of wrongdoing.';

export function FunderDashboard({ data }: { data: DashboardData }) {
  if (data.kind !== 'funder') return null;
  const mode = data.portfolio.status === 'ok' ? dataModeFor(data.portfolio.data.simulated.map((r) => r.project)) : 'observed';
  return (
    <div className={styles.dashboard} data-dashboard="funder">
      <SetDataMode mode={mode} />
      <Question text={FUNDER_QUESTION} help={FUNDER_HELP} />
      <Region id="portfolio" label="Portfolio" wide>
        <Slot panel={data.portfolio} title="Portfolio" render={(p) => <PortfolioTable data={p} />} />
      </Region>
      <Region id="needs-attention" title="Needs attention" wide collapsible badge="Action prompts">
        <Slot
          panel={data.portfolio}
          title="Needs attention"
          render={(p) => {
            const items = needsAttention(p.projects);
            if (items.length === 0) {
              const none = p.projects.length === 0 && p.simulated.length === 0;
              return <p className={styles.muted}>{none ? 'No projects are shared with your organization yet.' : 'No real project currently has a field that calls for review.'}</p>;
            }
            return (
              <>
                <p className={styles.muted}>Prompts for review drawn from served fields. They describe the state of the evidence, not the conduct of any project.</p>
                <ul className={styles.attention}>
                  {items.map((i) => (
                    <li key={i.id} data-attention-project={i.slug}>
                      <strong>{i.name}</strong>
                      <ul>
                        {i.reasons.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </>
            );
          }}
        />
      </Region>
      <Region id="activity" label="Recent activity" collapsible badge="Audit trail">
        <Slot panel={data.activity} title="Recent activity" render={(items) => <ActivityFeed items={items} />} />
      </Region>
    </div>
  );
}
