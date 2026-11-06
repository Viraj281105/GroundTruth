'use client';

import React from 'react';
import { useLens } from '../../lib/lens';
import { LENSES } from '../../lib/lens-core';
import { t } from '../../lib/i18n';
import styles from './Toggles.module.css';

/** Segmented control: how much detail pages reveal (Story → Explorer → Auditor). */
export function LensSwitch() {
  const { lens, setLens } = useLens();
  return (
    <div className={styles.segmented} role="radiogroup" aria-label="Level of detail">
      {LENSES.map((name) => (
        <button key={name} type="button" role="radio" aria-checked={lens === name} className={`${styles.segment} ${lens === name ? styles.segmentOn : ''}`} onClick={() => setLens(name)}>
          {t(`lens.${name}`)}
        </button>
      ))}
    </div>
  );
}
