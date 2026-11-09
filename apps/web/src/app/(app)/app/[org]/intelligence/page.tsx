import React from 'react';
import { GroqIntelligenceWorkspace } from '../../../../../components/panels/GroqIntelligenceWorkspace';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Environmental Intelligence & Groq LPU Research — GroundTruth 2.0' };

export default async function IntelligencePage({ params }: { params: { org: string } }) {
  return <GroqIntelligenceWorkspace orgSlug={params.org} />;
}

