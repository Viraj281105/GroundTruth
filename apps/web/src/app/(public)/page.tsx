import React from 'react';
import { CounterfactualHero } from '../../features/home/CounterfactualHero';
import { Divider, TrustFacts } from '../../features/home/Basics';
import { Problem } from '../../features/home/Problem';
import { HowSteps } from '../../features/home/HowSteps';
import { Features } from '../../features/home/Features';
import { AiFlow } from '../../features/home/AiFlow';
import { Faq, FinalCta, HonestStatus } from '../../features/home/Closing';

/**
 * Static marketing page. Signed-out visitors cannot read project data (the API answers 401), so
 * nothing here calls the API: the case count is deliberately omitted (`caseCount={null}`).
 */
export default function HomePage() {
  return (
    <>
      <CounterfactualHero />
      <TrustFacts caseCount={null} />
      <Divider />
      <Problem />
      <Divider />
      <HowSteps />
      <Divider />
      <Features />
      <Divider />
      <AiFlow />
      <Divider />
      <HonestStatus />
      <Faq />
      <FinalCta />
    </>
  );
}
