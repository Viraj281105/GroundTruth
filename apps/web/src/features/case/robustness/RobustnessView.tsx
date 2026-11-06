'use client';

import React, { useState } from 'react';
import { useParams } from 'next/navigation';
import { Lens } from '../../../lib/lens';
import type { Evidence } from '../../../lib/types';
import { deriveSpecCurve } from '../../../lib/spec-curve';
import { SpecificationCurve } from '../../../components/scientific/SpecificationCurve';
import { DidCrossCheck } from '../../../components/scientific/DidCrossCheck';
import { ProvenanceDrawer } from '../../../components/ui/ProvenanceDrawer';
import { CaseDataGate } from '../evidence/CaseDataGate';
import { useCaseEvidence } from '../evidence/useCaseEvidence';
import { Section, Term } from '../evidence/Term';
import { COPY } from '../evidence/copy';
import evidenceStyles from '../evidence/evidence.module.css';
import { Multiverse } from './Multiverse';

export function RobustnessView() {
  const params = useParams();
  const caseId = (params?.id as string) || 'kariba-redd';
  const state = useCaseEvidence(caseId);
  const [selected, setSelected] = useState<Evidence | null>(null);

  return (
    <div className={evidenceStyles.page}>
      <CaseDataGate state={state} caseId={caseId}>
        {({ items, isDemo }) => {
          const curve = deriveSpecCurve(items);
          return (
            <>
              {isDemo && <p className={evidenceStyles.empty}>{COPY.demoNote}</p>}
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
                    <Multiverse curve={curve} onSelect={(s) => setSelected(s.item)} />
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
                <DidCrossCheck items={items} onSelectEvidence={setSelected} />
              </Section>
            </>
          );
        }}
      </CaseDataGate>
      <ProvenanceDrawer evidence={selected} isOpen={selected !== null} onClose={() => setSelected(null)} />
    </div>
  );
}
