'use client';

import React, { useState } from 'react';
import { useParams } from 'next/navigation';
import { Lens } from '../../../lib/lens';
import { findEvidence, numberValue } from '../../../lib/evidence';
import type { Evidence } from '../../../lib/types';
import { CounterfactualChart } from '../../../components/scientific/CounterfactualChart';
import { FitDiagnostics } from '../../../components/scientific/FitDiagnostics';
import { PlaceboDistribution } from '../../../components/scientific/PlaceboDistribution';
import { PlaceboDiagnostics } from '../../../components/scientific/PlaceboDiagnostics';
import { DonorPoolPanel } from '../../../components/scientific/DonorPoolPanel';
import { DonorCandidatePanel } from '../../../components/scientific/DonorCandidatePanel';
import { ProvenanceDrawer } from '../../../components/ui/ProvenanceDrawer';
import { getDonorCandidateSummary } from '../../../lib/api';
import { Playground } from '../playground/Playground';
import { DonorMap } from '../map/DonorMap';
import { CaseDataGate } from './CaseDataGate';
import { useCaseEvidence } from './useCaseEvidence';
import { Section, Term } from './Term';
import { COPY } from './copy';
import styles from './evidence.module.css';

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
          return (
            <>
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
              </Section>

              <Section
                id="fit"
                title={COPY.sections.fit.title}
                lead={
                  <>
                    {COPY.sections.fit.lead} <Term id="pre-fit" />
                  </>
                }
              >
                <FitDiagnostics items={items} onSelectEvidence={setSelected} />
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
                {viz ? <PlaceboDistribution data={viz.placebos} /> : <p className={styles.empty}>{COPY.placeboMissing}</p>}
                <Lens show="explorer">
                  <PlaceboDiagnostics items={items} onSelectEvidence={setSelected} />
                </Lens>
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
                <DonorPoolPanel items={items} candidates={viz?.donorPool} onSelectEvidence={setSelected} />
                <Lens show="auditor">
                  {caseDetail && <DonorCandidatePanel summary={getDonorCandidateSummary(caseDetail)} />}
                </Lens>
                <DonorMap caseId={caseId} />
              </Section>

              <Section id="playground" title={COPY.sections.playground.title} lead={COPY.sections.playground.lead}>
                {viz ? (
                  <Playground caseId={caseId} series={viz.chartSeries} items={items} caseDetail={caseDetail} />
                ) : (
                  <p className={styles.empty}>{COPY.chartMissing}</p>
                )}
              </Section>
            </>
          );
        }}
      </CaseDataGate>
      <ProvenanceDrawer evidence={selected} isOpen={selected !== null} onClose={() => setSelected(null)} />
    </div>
  );
}
