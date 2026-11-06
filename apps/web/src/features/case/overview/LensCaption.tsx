'use client';

import React from 'react';
import { useLens } from '../../../lib/lens';
import styles from './overview.module.css';

export const lensCaptions = {
  story: 'Story view: plain language. Switch to Explorer for the evidence.',
  explorer: 'Explorer view: charts and plain-language definitions. Switch to Auditor for ids and raw evidence.',
  auditor: 'Auditor view: everything, including provenance ids, diagnostics and the raw evidence table.',
} as const;

/** One line under the page header saying which detail level is showing and what it contains. */
export function LensCaption() {
  const { lens } = useLens();
  return (
    <p className={styles.lensCaption} role="note">
      {lensCaptions[lens]}
    </p>
  );
}

/** Renders children only in the Story lens (the inverse of <Lens show>). */
export function StoryOnly({ children }: { children: React.ReactNode }) {
  const { lens } = useLens();
  return lens === 'story' ? <>{children}</> : null;
}

/** Renders children only in Explorer and Auditor (hidden in Story). */
export function NotStory({ children }: { children: React.ReactNode }) {
  const { lens } = useLens();
  return lens === 'story' ? null : <>{children}</>;
}
