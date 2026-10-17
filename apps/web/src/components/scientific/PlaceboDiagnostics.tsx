'use client';

import React from 'react';
import { Evidence } from '../../lib/types';
import { derivePlaceboDiagnostics } from '../../lib/placebo-diagnostics';
import { DiagnosticPanel } from './DiagnosticPanel';

/** In-space placebo, in-time placebo and leave-one-donor-out sensitivity. */
export const PlaceboDiagnostics: React.FC<{
  items: Evidence[];
  onSelectEvidence: (item: Evidence) => void;
}> = ({ items, onSelectEvidence }) => (
  <DiagnosticPanel
    id="placebo-diagnostics"
    title="Placebo & sensitivity tests"
    description="Whether the estimated divergence could arise without the project, at another date, or from a single comparison region."
    groups={derivePlaceboDiagnostics(items)}
    onSelectEvidence={onSelectEvidence}
  />
);
