'use client';

import React from 'react';
import { useLens } from '../../lib/lens';
import { useToast } from '../ds/Overlay';
import { LENSES } from '../../lib/lens-core';
import { t } from '../../lib/i18n';
import styles from './Toggles.module.css';

/** Segmented control: how much detail pages reveal (Story → Explorer → Auditor). */
const DESCRIPTIONS: Record<string, string> = {
  story: 'Story: the verdict in plain language, one number and one chart.',
  explorer: 'Explorer: adds the interactive evidence, donors, placebo and robustness.',
  auditor: 'Auditor: everything, including diagnostics, provenance ids and hashes.',
};

export function LensSwitch() {
  const { lens, setLens } = useLens();
  const toast = useToast();
  return (
    <div className={styles.segmented} role="radiogroup" aria-label="Level of detail">
      {LENSES.map((name) => (
        <button key={name} type="button" role="radio" aria-checked={lens === name} className={`${styles.segment} ${lens === name ? styles.segmentOn : ''}`} onClick={() => {
            setLens(name);
            toast(DESCRIPTIONS[name]);
          }} title={DESCRIPTIONS[name]}>
          {t(`lens.${name}`)}
        </button>
      ))}
    </div>
  );
}
