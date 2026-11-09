import React from 'react';
import Link from 'next/link';
import { t } from '../../lib/i18n';
import styles from './Footer.module.css';

export function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={`gt-container ${styles.inner}`}>
        <p className={styles.line}>
          <strong>GroundTruth</strong> · Independent causal screening of climate restoration and carbon-credit claims.
        </p>
        <p className={styles.note}>
          <Link href="/method">How it works</Link> · <Link href="/app">Workspace</Link> · <Link href="/claims">Claims workbench</Link>
        </p>
        <p className={styles.note}>{t('footer.note')}</p>
        <p className={styles.note}>NDVI is not carbon. Observed change is not causal effect. {t('sim.explain')}</p>
      </div>
    </footer>
  );
}
