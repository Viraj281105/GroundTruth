'use client';

import React from 'react';
import Link from 'next/link';
import { Check, ChevronRight } from 'lucide-react';
import { STATUS_LABEL, progressSummary, type LifecycleStep } from './lifecycle.model';
import styles from './LifecycleProgress.module.css';

const hrefFor = (orgSlug: string, projectSlug: string, step: LifecycleStep) =>
  step.segment === null ? `/app/${orgSlug}/projects` : `/app/${orgSlug}/projects/${projectSlug}/${step.segment}`;

function bubble(step: LifecycleStep) {
  if (step.status === 'done') return <Check size={12} strokeWidth={3} aria-hidden="true" />;
  if (step.status === 'blocked') return <span aria-hidden="true">!</span>;
  if (step.status === 'unavailable') return <span aria-hidden="true">–</span>;
  if (step.status === 'unknown') return <span aria-hidden="true">?</span>;
  return <span>{step.id}</span>;
}

/**
 * Project progress. Each step is a real page and carries a status computed from real data by
 * `lifecycleSteps` (see lifecycle.model.ts); nothing here asserts that something happened.
 */
export function LifecycleProgress({ orgSlug, projectSlug, steps }: { orgSlug: string; projectSlug: string; steps: readonly LifecycleStep[] }) {
  const { done, total, next } = progressSummary(steps);

  return (
    <div className={styles.container} role="region" aria-label="Project progress">
      <div className={styles.header}>
        <div className={styles.titleWrap}>
          <span className={styles.eyebrow}>Project progress</span>
          <span className={styles.activeStepIndicator}>
            <strong>
              {done} of {total}
            </strong>{' '}
            steps done
          </span>
        </div>
        <div className={styles.actionAdvice}>
          {next ? (
            <>
              <span className={styles.contextAdvice}>{next.description}</span>
              <Link href={hrefFor(orgSlug, projectSlug, next)} className={styles.nextActionBtn}>
                <span>Next: {next.shortLabel}</span>
                <ChevronRight size={14} aria-hidden="true" />
              </Link>
            </>
          ) : (
            <span className={styles.contextAdvice}>No step is waiting on you. Steps marked not available cannot be done for this project.</span>
          )}
        </div>
      </div>

      <nav className={styles.track} aria-label="Project steps">
        <ol className={styles.stepList}>
          {steps.map((step, idx) => (
            <li
              key={step.id}
              className={[
                styles.stepItem,
                step.status === 'done' ? styles.completed : '',
                step.status === 'current' ? styles.active : '',
                step.status === 'blocked' || step.status === 'unavailable' || step.status === 'unknown' ? styles.muted : '',
                step.status === 'blocked' ? styles.blocked : '',
              ].join(' ')}
              data-step-status={step.status}
              aria-current={step.status === 'current' ? 'step' : undefined}
            >
              <Link href={hrefFor(orgSlug, projectSlug, step)} className={styles.stepLink} title={`${step.label} (${STATUS_LABEL[step.status]}): ${step.description}`}>
                <span className={styles.bubble}>{bubble(step)}</span>
                <span className={styles.stepLabel}>{step.shortLabel}</span>
                <span className={styles.srOnly}>{STATUS_LABEL[step.status]}</span>
              </Link>
              {idx < steps.length - 1 && <span className={styles.connector} aria-hidden="true" />}
            </li>
          ))}
        </ol>
      </nav>
    </div>
  );
}
