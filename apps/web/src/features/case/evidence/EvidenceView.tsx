'use client';

import React, { useState } from 'react';
import { useParams } from 'next/navigation';
import { Lens } from '../../../lib/lens';
import { findEvidence, numberValue } from '../../../lib/evidence';
import type { Evidence } from '../../../lib/types';
import { BarList, LineChart } from '../../../components/charts';
import { BinnedHistogram } from '../../../components/charts/BinnedHistogram';
import { CounterfactualChart } from '../../../components/scientific/CounterfactualChart';
import { FitDiagnostics } from '../../../components/scientific/FitDiagnostics';
import { PlaceboDiagnostics } from '../../../components/scientific/PlaceboDiagnostics';
import { DonorPoolPanel } from '../../../components/scientific/DonorPoolPanel';
import { DonorCandidatePanel } from '../../../components/scientific/DonorCandidatePanel';
import { ProvenanceDrawer } from '../../../components/ui/ProvenanceDrawer';
import { getDonorCandidateSummary } from '../../../lib/api';
import { Playground } from '../playground/Playground';
import { DonorMap } from '../map/DonorMap';
import { AuditTables } from './AuditTables';
import { CaseDataGate } from './CaseDataGate';
import { useCaseEvidence } from './useCaseEvidence';
import { Section, Term } from './Term';
import { BigNumbers, Card, FitAndPDonuts, LensCaption, TimelineStrip } from './VizBits';
import { donorBars, gapSeries, placeboBins, storyNumbers, storySentence } from './viz-model';
import { COPY } from './copy';
import styles from './evidence.module.css';
import vz from './viz.module.css';

export function EvidenceView() {
  const params = useParams();
  const caseId = (params?.id as string) || 'kariba-redd';
  const state = useCaseEvidence(caseId);
  const [selected, setSelected] = useState<Evidence | null>(null);

  return (
    <div className={styles.page}>
      <CaseDataGate state={state} caseId={caseId}>
        {({ caseDetail, items, viz, isDemo }) => {
          const treatmentYear =
            numberValue(findEvidence(items, 'fit.treatment_boundary_period')) ??
            (caseDetail ? parseInt(caseDetail.post_period.split('-')[0], 10) : undefined);
          const gap = viz ? gapSeries(viz.chartSeries) : [];
          const bars = donorBars(items);
          return (
            <>
              <LensCaption />
              {isDemo && <p className={styles.empty}>{COPY.demoNote}</p>}

              <Section
                id="chart"
                title={COPY.sections.chart.title}
                lead={
                  <>
                    {COPY.sections.chart.lead} <Term id="counterfactual" />
                  </>
                }
              >
                {viz && caseDetail ? (
                  <CounterfactualChart
                    data={viz.chartSeries}
                    treatmentYear={treatmentYear}
                    indicator={caseDetail.indicator}
                    indicatorUnit={caseDetail.indicator}
                    evidence={items}
                  />
                ) : (
                  <p className={styles.empty}>{COPY.chartMissing}</p>
                )}
                <p className={vz.sentence}>{storySentence(items, treatmentYear)}</p>
                <BigNumbers numbers={storyNumbers(items, viz?.placebos)} />
              </Section>

              <Lens show="explorer">
                <Section
                  id="fit"
                  title={COPY.sections.fit.title}
                  lead={
                    <>
                      {COPY.sections.fit.lead} <Term id="pre-fit" />
                    </>
                  }
                >
                  <div className={vz.grid}>
                    <Card title="Pre-period fit and placebo p" note="Fit is drawn against the engine's own gate; the p-value is the add-one placebo rank.">
                      <FitAndPDonuts items={items} viz={viz} />
                    </Card>
                    <Card title="Gap after the intervention" note="Observed minus counterfactual, per period, as returned.">
                      {gap.length > 0 ? (
                        <LineChart series={gap} refX={treatmentYear} refLabel="intervention" height={190} label="Gap between observed and counterfactual by year" />
                      ) : (
                        <p className={styles.empty}>Not available: no per-period series was provided.</p>
                      )}
                    </Card>
                  </div>
                </Section>

                <Section
                  id="placebo"
                  title={COPY.sections.placebo.title}
                  lead={
                    <>
                      {COPY.sections.placebo.lead} <Term id="placebo" /> <Term id="p-value" />
                    </>
                  }
                >
                  <Card title="Project effect against placebo areas" note={viz ? `${viz.placebos.totalUnits} units; the marked line is the project area.` : undefined}>
                    {viz ? (
                      <BinnedHistogram bins={placeboBins(viz.placebos)} marker={viz.placebos.projectStatistic} markerLabel="project area" label="Distribution of placebo effects with the project effect marked" />
                    ) : (
                      <p className={styles.empty}>{COPY.placeboMissing}</p>
                    )}
                  </Card>
                </Section>

                <Section
                  id="donors"
                  title={COPY.sections.donors.title}
                  lead={
                    <>
                      {COPY.sections.donors.lead} <Term id="donor-pool" />
                    </>
                  }
                >
                  <div className={vz.grid}>
                    <Card title="Largest donor weights" note="Share of the counterfactual each comparison area carries.">
                      {bars.length > 0 ? <BarList items={bars} label="Largest donor weights in percent" /> : <p className={styles.empty}>Not available: the run did not report donor weights.</p>}
                    </Card>
                    <Card title="Project timeline">{viz ? <TimelineStrip events={viz.timeline} /> : <p className={styles.empty}>Not available: no timeline was provided.</p>}</Card>
                  </div>
                  <DonorMap caseId={caseId} />
                </Section>

                <Section id="playground" title={COPY.sections.playground.title} lead={COPY.sections.playground.lead}>
                  {viz ? <Playground caseId={caseId} series={viz.chartSeries} items={items} caseDetail={caseDetail} /> : <p className={styles.empty}>{COPY.chartMissing}</p>}
                </Section>
              </Lens>

              <Lens show="auditor">
                <Section id="audit" title="Residuals, donors and provenance" lead="Raw values behind the charts. Select an evidence id to open its provenance.">
                  <AuditTables items={items} viz={viz} onSelect={setSelected} />
                  <FitDiagnostics items={items} onSelectEvidence={setSelected} />
                  <PlaceboDiagnostics items={items} onSelectEvidence={setSelected} />
                  <DonorPoolPanel items={items} candidates={viz?.donorPool} onSelectEvidence={setSelected} />
                  {caseDetail && <DonorCandidatePanel summary={getDonorCandidateSummary(caseDetail)} />}
                </Section>
              </Lens>
            </>
          );
        }}
      </CaseDataGate>
      <ProvenanceDrawer evidence={selected} isOpen={selected !== null} onClose={() => setSelected(null)} />
    </div>
  );
}
