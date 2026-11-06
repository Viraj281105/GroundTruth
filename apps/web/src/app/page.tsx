import React from 'react';
import { getCases, getVisualizationFixture } from '../lib/api';
import type { CaseSummary } from '../lib/types';
import { CounterfactualHero } from '../features/home/CounterfactualHero';
import { buildCaseViz, observedSeriesMap } from '../features/cases/viz';
import { FeaturedCases, FeaturedStrip, HowItWorks, StatusLine } from '../features/home/HomeSections';

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
  const featured = cases.find((x) => series[x.case_id]);
  const viz = featured ? buildCaseViz(getVisualizationFixture(featured.case_id)) : null;
  return (
    <>
      <CounterfactualHero />
      <HowItWorks />
      {featured && viz && <FeaturedStrip name={featured.name} caseId={featured.case_id} viz={viz} />}
      <FeaturedCases cases={cases} failed={failed} series={series} />
      <StatusLine />
    </>
  );
}
