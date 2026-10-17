'use client';

import React from 'react';
import { Evidence } from '../../lib/types';
import { deriveFitDiagnostics } from '../../lib/fit-diagnostics';
import { DiagnosticPanel } from './DiagnosticPanel';

/** Pre-treatment fit, convex-hull containment and period coverage. */
export const FitDiagnostics: React.FC<{
  items: Evidence[];
  onSelectEvidence: (item: Evidence) => void;
}> = ({ items, onSelectEvidence }) => (
  <DiagnosticPanel
    id="fit-diagnostics"
    title="Fit & identification diagnostics"
    description="Conditions the counterfactual must meet before its post-treatment gap can be read as an effect."
    groups={deriveFitDiagnostics(items)}
    onSelectEvidence={onSelectEvidence}
  />
);
