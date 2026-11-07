import React from 'react';
import { getCases, getVisualizationFixture } from '../lib/api';
import type { CaseSummary } from '../lib/types';
import { CounterfactualHero } from '../features/home/CounterfactualHero';
import { observedSeriesMap } from '../features/cases/viz';
import { Divider, TrustFacts } from '../features/home/Basics';
import { Problem } from '../features/home/Problem';
import { HowSteps } from '../features/home/HowSteps';
import { Features } from '../features/home/Features';
import { AiFlow } from '../features/home/AiFlow';
import { TryCases } from '../features/home/TryCases';
import { Faq, FinalCta, HonestStatus } from '../features/home/Closing';

export const dynamic = 'force-dynamic';

export default async function HomePage() {
  let cases: CaseSummary[] = [];
  let failed = false;
  try {
    cases = (await getCases()).data;
  } catch {
    failed = true;
  }
  const series = observedSeriesMap(cases.map((x) => x.case_id), getVisualizationFixture);
  return (
    <>
      <CounterfactualHero />
      <TrustFacts caseCount={failed ? null : cases.length} />
      <Divider />
      <Problem />
      <Divider />
      <HowSteps />
      <Divider />
      <Features />
      <Divider />
      <AiFlow />
      <Divider />
      <TryCases cases={cases} failed={failed} series={series} />
      <Divider />
      <HonestStatus />
      <Faq />
      <FinalCta />
    </>
  );
}
