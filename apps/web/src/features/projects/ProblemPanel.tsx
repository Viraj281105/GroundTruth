import React from 'react';
import { UnavailablePanel } from '../../components/ds/UnavailablePanel';
import { apiErrorMessage } from './model';

/** One honest panel for a failed fetch: status-specific reason, and what would unlock it. Never substitute data. */
export function ProblemPanel({ title, status, needs }: { title: string; status: number; needs?: string }) {
  return <UnavailablePanel title={title} reason={apiErrorMessage(status)} evidenceNeeded={needs ?? 'A reachable API and sufficient access to this project. No substitute data is shown.'} />;
}
