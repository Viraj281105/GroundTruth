'use client';

import React from 'react';
import { Evidence } from '../../lib/types';
import { deriveDidDiagnostics } from '../../lib/did-diagnostics';
import { DiagnosticPanel } from './DiagnosticPanel';

/** Difference-in-differences cross-check with its cluster-robust inference. */
export const DidCrossCheck: React.FC<{
  items: Evidence[];
  onSelectEvidence: (item: Evidence) => void;
}> = ({ items, onSelectEvidence }) => (
  <DiagnosticPanel
    id="did-crosscheck"
    title="Cross-check estimator"
    description="A second estimator that is valid only under parallel trends. Disagreement with the synthetic control is reported, not resolved."
    groups={deriveDidDiagnostics(items)}
    columns={2}
    onSelectEvidence={onSelectEvidence}
  />
);
