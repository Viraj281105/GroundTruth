import React from 'react';
import { Card, DataModeBanner } from '../ds';
import { DimensionCard } from './DimensionCard';
import { RecommendationList } from './RecommendationList';
import { PanelEmpty, PanelLoading } from './PanelStates';
import { levelLadder } from './level.model';
import { limitationLabel } from './dimension.model';
import { titleCase } from './format';
import type { AssessmentView, ConclusionView, PanelProps } from './types';
import styles from './panels.module.css';

function Conclusion({ title, c }: { title: string; c: ConclusionView }) {
  const ok = c.estimable;
  return (
    <div className={`${styles.conclusion} ${ok ? '' : styles.notEstimable}`} data-estimable={ok}>
      <h3>{title}</h3>
      {ok ? <p>{c.summary}</p> : <p>Not estimable. {c.reason ?? 'No reason was reported.'}</p>}
      {ok && c.reason && <p className={styles.muted}>{c.reason}</p>}
    </div>
  );
}

export interface AssessmentSummaryProps extends PanelProps<AssessmentView> {
  /** Org type of the viewer; recommendations are ordered for it. */
  persona?: string | null;
}

/** Level badge + ladder, layered conclusions, the eight dimensions and the recommendations. */
export function AssessmentSummary({ data, loading, persona }: AssessmentSummaryProps) {
  if (loading) return <PanelLoading label="assessment" />;
  if (!data) return <PanelEmpty title="No assessment yet" body="An assessment appears once the project has evidence to assess." />;
  const ladder = levelLadder(data.level, data.level_name);
  const a = data.attribution;
  return (
    <section className={styles.panel} aria-label="Assessment">
      <DataModeBanner mode={data.data_mode} />
      <div className={styles.head}>
        <span className={styles.levelBadge} data-level={ladder.level}>
          {ladder.badge}
        </span>
        <span className={styles.muted}>Evidence confidence: {data.evidence_confidence}</span>
      </div>
      <ol className={styles.ladder} aria-label="Assessment level ladder">
        {ladder.steps.map((s) => (
          <li key={s.level} className={`${styles.step} ${styles[s.state]}`} data-ladder-step={s.level} data-ladder-state={s.state}>
            <span className={styles.stepMark} aria-hidden="true">
              {s.level}
            </span>
            <span className={styles.stepName}>
              {s.name}
              <span className={styles.stepState}>{s.state === 'current' ? 'reached level' : s.state === 'reached' ? 'reached' : 'not reached'}</span>
            </span>
          </li>
        ))}
      </ol>
      <div className={styles.conclusions}>
        <Conclusion title="Observed outcome" c={data.observed_outcome} />
        <Conclusion title="Ecological assessment" c={data.ecological_assessment} />
        <Conclusion title="Climate-adjusted interpretation" c={data.climate_adjusted_interpretation} />
        <Conclusion title="Comparative assessment" c={data.comparative_assessment} />
        <div className={styles.conclusion} data-attribution-verdict={a.verdict}>
          <h3>Attribution verdict</h3>
          <p>
            <strong>{a.verdict}</strong>. {a.finding}
          </p>
          <p className={styles.muted}>Methodology: {a.methodology}</p>
          <p className={styles.muted}>Limitation: {limitationLabel(a.limitation)}</p>
          {a.evidence_needed && <p className={styles.muted}>Evidence needed: {a.evidence_needed}</p>}
        </div>
        <div className={styles.conclusion}>
          <h3>Evidence confidence</h3>
          <p>
            <strong>{data.evidence_confidence}</strong>
          </p>
        </div>
      </div>
      {(data.dimensions ?? []).length === 0 ? (
        <p className={styles.notice}>No dimension results available for this project.</p>
      ) : (
        <div className={styles.dimGrid}>
          {data.dimensions.map((d) => (
            <DimensionCard key={d.id} dimension={d} />
          ))}
        </div>
      )}
      <Card>
        <h3 className={styles.title}>{titleCase('recommendations')}</h3>
        <RecommendationList recommendations={data.recommendations} persona={persona} />
      </Card>
    </section>
  );
}
