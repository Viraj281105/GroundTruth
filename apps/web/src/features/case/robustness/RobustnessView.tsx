'use client';

import React, { useState } from 'react';
import { useParams } from 'next/navigation';
import { Lens } from '../../../lib/lens';
import type { Evidence } from '../../../lib/types';
import { deriveSpecCurve } from '../../../lib/spec-curve';
import { BarList, HistogramChart } from '../../../components/charts';
import { SignedBars } from '../../../components/charts/SignedBars';
import { SpecDots } from '../../../components/charts/SpecDots';
import { SpecificationCurve } from '../../../components/scientific/SpecificationCurve';
import { DidCrossCheck } from '../../../components/scientific/DidCrossCheck';
import { ProvenanceDrawer } from '../../../components/ds/ProvenanceDrawer';
import { CaseDataGate } from '../evidence/CaseDataGate';
import { useCaseEvidence } from '../evidence/useCaseEvidence';
import { Section, Term } from '../evidence/Term';
import { Card, LensCaption } from '../evidence/VizBits';
import { didVsScm, leaveOneOutBars, specDots, specValues } from '../evidence/viz-model';
import { EvidenceScope, KindBadge, SourceBanner } from '../evidence/EvidenceProvenance';
import evidenceStyles from '../evidence/evidence.module.css';
import vz from '../evidence/viz.module.css';
import { Multiverse } from './Multiverse';

export function RobustnessView() {
  const params = useParams();
  const caseId = (params?.id as string) || 'kariba-redd';
  const state = useCaseEvidence(caseId);
  const [selected, setSelected] = useState<Evidence | null>(null);

  return (
    <div className={evidenceStyles.page}>
      <CaseDataGate state={state} caseId={caseId}>
        {({ items, origin, runId }) => {
          const curve = deriveSpecCurve(items);
          const pair = didVsScm(items);
          const loo = leaveOneOutBars(items);
          return (
            <>
              <LensCaption />
              <SourceBanner origin={origin} runId={runId} />
              <KindBadge kind="derived-analysis" />
              <EvidenceScope caseId={caseId} />
              <Section
                id="multiverse"
                title="Does the answer depend on how the analysis was set up?"
                lead={
                  <>
                    Each point is one reasonable way to run the analysis, changing a single choice at a time. If the points stay together, the
                    result does not hinge on one choice. <Term id="spec-curve" />
                  </>
                }
              >
                {curve ? (
                  <>
                    <p className={evidenceStyles.lead}>{curve.summary}</p>
                    <Card title="Every specification, ordered by estimate" note="The large point is the request's own specification; the dashed line is zero.">
                      <SpecDots dots={specDots(curve)} unit={curve.unit} label={`${curve.nSpecifications} specifications ordered by estimate`} />
                    </Card>
                    <Lens show="explorer">
                      <div className={vz.grid}>
                        <Card title="Spread of the estimates">
                          <HistogramChart values={specValues(curve)} bins={10} label="Histogram of specification estimates" />
                        </Card>
                        <Card title="The same points by choice varied">
                          <Multiverse curve={curve} onSelect={(s) => setSelected(s.item)} />
                        </Card>
                      </div>
                    </Lens>
                    <Lens show="auditor">
                      <SpecificationCurve items={items} onSelectEvidence={setSelected} />
                    </Lens>
                  </>
                ) : (
                  <p className={evidenceStyles.empty}>
                    Not measured. The specification curve was not run for this analysis, so the estimate has not been tested against alternative
                    analytic choices here.
                  </p>
                )}
              </Section>

              <Lens show="explorer">
                <Section
                  id="did"
                  title="Does a second method agree?"
                  lead={
                    <>
                      A simpler estimator, valid only if the project and comparison areas were moving in parallel before the intervention.{' '}
                      <Term id="did" /> <Term id="parallel-trends" />
                    </>
                  }
                >
                  <div className={vz.grid}>
                    <Card title="Synthetic control vs difference-in-differences" note="Disagreement is reported, not resolved.">
                      {pair.length > 0 ? <SignedBars items={pair} label="Effect estimate by method" /> : <p className={evidenceStyles.empty}>Not measured: the cross-check was not run.</p>}
                    </Card>
                    <Card title="Removing one donor at a time" note="Compares the largest shift with the size of the estimate.">
                      {loo.length > 0 ? <BarList items={loo} label="Largest leave-one-donor-out shift against the estimate" /> : <p className={evidenceStyles.empty}>Not measured for this analysis.</p>}
                    </Card>
                  </div>
                  <Lens show="auditor">
                    <DidCrossCheck items={items} onSelectEvidence={setSelected} />
                  </Lens>
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
