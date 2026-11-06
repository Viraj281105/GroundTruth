'use client';

import React, { useMemo, useReducer } from 'react';
import { Button, Chip, LinkButton } from '../../../components/ds';
import { CounterfactualChart } from '../../../components/scientific/CounterfactualChart';
import { sig } from '../../../lib/evidence';
import type { ChartDataPoint } from '../../../lib/fixtures/simulated-data';
import type { CaseDetail, Evidence } from '../../../lib/types';
import { Term } from '../evidence/Term';
import { LineChart } from '../../../components/charts';
import { gapSeries } from '../evidence/viz-model';
import {
  derivePlaygroundView,
  deriveDonorWeights,
  engineTreatmentYear,
  initialPlaygroundState,
  playgroundReducer,
  rerunHref,
  reshadeSeries,
} from './playground-model';
import styles from './playground.module.css';

export function Playground({
  caseId,
  series,
  items,
  caseDetail,
}: {
  caseId: string;
  series: ChartDataPoint[];
  items: Evidence[];
  caseDetail: CaseDetail | null;
}) {
  const years = series.map((p) => p.year);
  const engineYear = engineTreatmentYear(items, series);
  const donors = useMemo(() => deriveDonorWeights(items), [items]);
  const [state, dispatch] = useReducer(
    playgroundReducer,
    initialPlaygroundState(engineYear ?? years[0] ?? 0, Math.min(...years), Math.max(...years)),
  );
  const view = useMemo(() => derivePlaygroundView(state, series, donors, items), [state, series, donors, items]);
  const shaded = useMemo(() => reshadeSeries(series, state.year), [series, state.year]);

  const gap = useMemo(() => gapSeries(series), [series]);
  const postCount = shaded.filter((p) => p.isPost).length;

  if (series.length === 0 || engineYear === null) return null;

  return (
    <div className={styles.root}>
      <div className={styles.controls}>
        <div className={styles.field}>
          <label htmlFor="pg-year" className={styles.label}>
            Intervention year: <strong>{state.year}</strong>
            {state.year === state.engineYear && <Chip tone="accent">engine&apos;s year</Chip>}
          </label>
          <input
            id="pg-year"
            className={styles.range}
            type="range"
            min={state.minYear}
            max={state.maxYear}
            step={1}
            value={state.year}
            onChange={(e) => dispatch({ type: 'setYear', year: Number(e.target.value) })}
            aria-valuetext={`Year ${state.year}`}
          />
        </div>

        <fieldset className={styles.donors}>
          <legend className={styles.label}>
            <Term id="donor-pool">Donors</Term> that carry the most weight
          </legend>
          {donors.length === 0 ? (
            <p className={styles.muted}>The API did not report donor weights for this run.</p>
          ) : (
            <ul className={styles.donorList}>
              {donors.map((d) => {
                const off = state.excluded.includes(d.id);
                return (
                  <li key={d.item.id}>
                    <label className={`${styles.donor} ${off ? styles.off : ''}`}>
                      <input
                        type="checkbox"
                        checked={!off}
                        onChange={() => dispatch({ type: 'toggleDonor', id: d.id })}
                      />
                      <span className={styles.donorName}>{d.id}</span>
                      <span className={styles.donorWeight}>{sig(d.weight * 100)}%</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </fieldset>
      </div>

      <CounterfactualChart
        data={shaded}
        treatmentYear={state.year}
        indicator={caseDetail?.indicator ?? ''}
        indicatorUnit={caseDetail?.indicator ?? ''}
        evidence={items}
      />

      {gap.length > 0 && (
        <div>
          <LineChart series={gap} refX={state.year} refLabel={`intervention ${state.year}`} height={170} label={`Gap by year with the intervention marked at ${state.year}`} />
          <p className={styles.muted}>
            {postCount} of {series.length} periods are counted as after the intervention at {state.year}.
          </p>
        </div>
      )}

      <div className={styles.readout} aria-live="polite">
        {view.point && (
          <p>
            In {state.year} the series shows observed {sig(view.point.observed)}, counterfactual {sig(view.point.synthetic)}, gap{' '}
            {sig(view.point.gap)}.
          </p>
        )}
        {view.engineEstimate ? (
          <p>
            Engine estimate for this setting: <strong>{sig(view.engineEstimate.value)} {view.engineEstimate.unit}</strong>
            <span className={styles.muted}> ({view.engineEstimate.label})</span>
          </p>
        ) : null}
        {view.removedWeight !== null && (
          <p>The donors switched off carry {sig(view.removedWeight * 100)}% of the reported weight.</p>
        )}
        {view.reason && <p className={styles.reason}>{view.reason}</p>}
        <p className={styles.muted}>
          The curves show the engine&apos;s full-pool counterfactual; only the shading and the marker follow the slider.
        </p>
      </div>

      <div className={styles.actions}>
        {view.needsRerun && (
          <LinkButton href={rerunHref(caseId, state)} variant="primary">
            Re-run with this change
          </LinkButton>
        )}
        <Button variant="ghost" onClick={() => dispatch({ type: 'reset' })} disabled={!view.changed}>
          Reset
        </Button>
      </div>
    </div>
  );
}
