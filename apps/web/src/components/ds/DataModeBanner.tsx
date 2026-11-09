import React from 'react';
import { t } from '../../lib/i18n';
import styles from './DataModeBanner.module.css';

export type DataMode = 'observed' | 'simulated';

/**
 * Persistent data-mode banner (R7). Renders nothing for observed data; for simulated data it
 * renders the existing simulated copy (`sim.chip` / `sim.explain`). The simulated colour is used
 * here and on the simulated chip only.
 */
export function DataModeBanner({ mode }: { mode: DataMode }) {
  if (mode !== 'simulated') return null;
  return (
    <div className={styles.banner} role="status" data-data-mode="simulated">
      <b className={styles.label}>{t('sim.chip')}</b>
      <span>{t('sim.explain')}</span>
    </div>
  );
}
