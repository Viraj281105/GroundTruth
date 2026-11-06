import React from 'react';
import { Card } from '../../components/ds';
import { BarList, LineChart, RangeBar } from '../../components/charts';
import type { CaseViz } from '../cases/viz';
import { COMPARE_COPY as C } from './copy';
import styles from './ComparePage.module.css';

export interface NamedViz {
  name: string;
  viz: CaseViz;
}

export function CompareCharts({ a, b }: { a: NamedViz; b: NamedViz }) {
  const both = [a, b];
  const treatment = a.viz.treatmentYear ?? b.viz.treatmentYear ?? undefined;
  const donorItems = both.flatMap((c) => c.viz.donorsAdmitted === null ? [] : [{ label: c.name, value: c.viz.donorsAdmitted, tone: 'accent' as const, display: String(c.viz.donorsAdmitted) }]);
  const fitItems = both.flatMap((c) => c.viz.relPreRmspe === null ? [] : [{ label: c.name, value: c.viz.relPreRmspe, tone: 'synthetic' as const, display: c.viz.relPreRmspe.toFixed(3) }]);
  const pItems = both.flatMap((c) => c.viz.placeboP === null ? [] : [{ label: c.name, value: c.viz.placeboP, tone: 'caution' as const, display: c.viz.placeboP.toFixed(3) }]);
  return (
    <section className={styles.charts} aria-labelledby="cmp-charts">
      <h2 id="cmp-charts" className={styles.chartsTitle}>{C.chartsTitle}</h2>
      <p className={styles.hint}>{C.chartsNote}</p>
      <Card>
        <h3 className={styles.h3}>{C.gapTitle}</h3>
        <LineChart
          label={`Observed minus synthetic gap over time for ${a.name} and ${b.name}`}
          refX={treatment}
          refLabel={treatment !== undefined ? String(treatment) : undefined}
          series={[
            { name: a.name, tone: 'observed', points: a.viz.gap },
            { name: b.name, tone: 'accent', points: b.viz.gap, dashed: true },
          ]}
        />
      </Card>
      <div className={styles.cols}>
        {both.map((c) => (
          <Card key={c.name}>
            <h3 className={styles.h3}>{c.name}</h3>
            {c.viz.effect !== null && c.viz.specLow !== null && c.viz.specHigh !== null ? (
              <>
                <RangeBar estimate={c.viz.effect} low={c.viz.specLow} high={c.viz.specHigh} unit={c.viz.indicator ? ` ${c.viz.indicator}` : ''} label={`Effect ${c.viz.effect.toFixed(3)} with specification range ${c.viz.specLow.toFixed(3)} to ${c.viz.specHigh.toFixed(3)}`} />
                <p className={styles.hint}>{C.rangeNote}</p>
              </>
            ) : (
              <p className={styles.missing}>{C.notAvailable}</p>
            )}
          </Card>
        ))}
      </div>
      <div className={styles.cols}>
        <Card><h3 className={styles.h3}>{C.donorsChart}</h3><BarList items={donorItems} label={C.donorsChart} /></Card>
        <Card><h3 className={styles.h3}>{C.fitChart}</h3><BarList items={fitItems} label={C.fitChart} /></Card>
        <Card><h3 className={styles.h3}>{C.pChart}</h3><BarList items={pItems} label={C.pChart} max={1} /></Card>
      </div>
    </section>
  );
}
