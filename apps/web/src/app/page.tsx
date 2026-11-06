import React from 'react';
import { getCases } from '../lib/api';
import type { CaseSummary } from '../lib/types';
import { CounterfactualHero } from '../features/home/CounterfactualHero';
import { FeaturedCases, HowItWorks, StatusLine } from '../features/home/HomeSections';

export const dynamic = 'force-dynamic';

export default async function HomePage() {
  let cases: CaseSummary[] = [];
  let failed = false;
  try {
    cases = (await getCases()).data;
  } catch {
    failed = true;
  }
  return (
    <>
      <CounterfactualHero />
      <HowItWorks />
      <FeaturedCases cases={cases} failed={failed} />
      <StatusLine />
    </>
  );
}
