'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Check, ChevronRight } from 'lucide-react';
import styles from './LifecycleProgress.module.css';

export interface LifecycleStep {
  id: number;
  label: string;
  shortLabel: string;
  segment: string;
  description: string;
}

export const LIFECYCLE_STEPS: readonly LifecycleStep[] = [
  { id: 1, label: 'Discover / Create', shortLabel: 'Create', segment: 'projects', description: 'Project registered in organization ledger' },
  { id: 2, label: 'Define Boundary', shortLabel: 'Boundary', segment: 'overview', description: 'GeoJSON treatment polygon validated' },
  { id: 3, label: 'Upload Documents', shortLabel: 'Documents', segment: 'evidence', description: 'Project design documents & baseline records' },
  { id: 4, label: 'Collect Evidence', shortLabel: 'Evidence', segment: 'observation', description: 'Sentinel-2 & remote sensing time-series ingested' },
  { id: 5, label: 'Run Assessment', shortLabel: 'Assessment', segment: 'climate', description: 'Climate shocks, drought radar & covariates computed' },
  { id: 6, label: 'Review Findings', shortLabel: 'Findings', segment: 'overview', description: 'Pre-trend checks & synthetic control diagnostics' },
  { id: 7, label: 'Verify Claims', shortLabel: 'Verify Claims', segment: 'verification', description: 'Decomposed 8-dimension claim verification' },
  { id: 8, label: 'Generate Report', shortLabel: 'Reports', segment: 'reports', description: 'Cryptographically sealed audit & CSR dossiers' },
  { id: 9, label: 'Monitor Progress', shortLabel: 'Monitor', segment: 'activity', description: 'Continuous satellite monitoring & audit telemetry' },
];

export function LifecycleProgress({ orgSlug, projectSlug }: { orgSlug: string; projectSlug: string }) {
  const pathname = usePathname() ?? '';
  const currentSegment = pathname.split('/').pop() || 'overview';

  // Determine current active step based on URL segment
  let activeIndex = LIFECYCLE_STEPS.findIndex((s) => s.segment === currentSegment);
  if (activeIndex === -1) {
    activeIndex = 6; // Default to Step 7 (Verify Claims)
  }

  const base = `/app/${orgSlug}/projects/${projectSlug}`;

  return (
    <div className={styles.container} role="region" aria-label="Project Lifecycle Progress">
      <div className={styles.header}>
        <div className={styles.titleWrap}>
          <span className={styles.eyebrow}>Guided Restoration Lifecycle</span>
          <span className={styles.activeStepIndicator}>
            Step {activeIndex + 1} of 9: <strong>{LIFECYCLE_STEPS[activeIndex]?.label}</strong>
          </span>
        </div>
        <div className={styles.actionAdvice}>
          <span className={styles.contextAdvice}>{LIFECYCLE_STEPS[activeIndex]?.description}</span>
          {activeIndex < 8 && (
            <Link href={`${base}/${LIFECYCLE_STEPS[activeIndex + 1]?.segment}`} className={styles.nextActionBtn}>
              <span>Next: {LIFECYCLE_STEPS[activeIndex + 1]?.shortLabel}</span>
              <ChevronRight size={14} aria-hidden="true" />
            </Link>
          )}
        </div>
      </div>

      <nav className={styles.track} aria-label="Lifecycle Steps">
        <ol className={styles.stepList}>
          {LIFECYCLE_STEPS.map((step, idx) => {
            const isCompleted = idx < activeIndex;
            const isCurrent = idx === activeIndex;
            const targetHref = step.segment === 'projects' ? `/app/${orgSlug}/projects` : `${base}/${step.segment}`;

            return (
              <li
                key={step.id}
                className={`${styles.stepItem} ${isCompleted ? styles.completed : ''} ${isCurrent ? styles.active : ''}`}
                aria-current={isCurrent ? 'step' : undefined}
              >
                <Link href={targetHref} className={styles.stepLink} title={`${step.label}: ${step.description}`}>
                  <span className={styles.bubble}>
                    {isCompleted ? <Check size={12} strokeWidth={3} aria-hidden="true" /> : <span>{step.id}</span>}
                  </span>
                  <span className={styles.stepLabel}>{step.shortLabel}</span>
                </Link>
                {idx < LIFECYCLE_STEPS.length - 1 && <span className={styles.connector} aria-hidden="true" />}
              </li>
            );
          })}
        </ol>
      </nav>
    </div>
  );
}

