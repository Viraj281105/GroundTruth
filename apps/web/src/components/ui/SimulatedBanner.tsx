import React from 'react';
import { AlertTriangle, Info } from 'lucide-react';
import styles from './SimulatedBanner.module.css';

export interface SimulatedBannerProps {
  message?: string;
  subtext?: string;
  className?: string;
}

/**
 * Persistent, non-dismissible banner displayed whenever data comes from a synthetic run.
 * RULE: The simulated-data banner is unmissable and cannot be dismissed.
 */
export const SimulatedBanner: React.FC<SimulatedBannerProps> = ({
  message = 'SIMULATED DATA RUN — SYNTHETIC TEST FIXTURE',
  subtext = 'This view displays output produced by the synthetic fixture provider. All figures describe a controlled simulation and must not be cited or published as findings regarding any real project.',
  className = '',
}) => {
  return (
    <div className={`${styles.banner} ${className}`} role="alert">
      <div className={styles.inner}>
        <div className={styles.iconCol}>
          <AlertTriangle className={styles.alertIcon} size={20} />
        </div>
        <div className={styles.textCol}>
          <div className={styles.titleRow}>
            <span className={styles.badge}>FIXTURE MODE</span>
            <strong className={styles.title}>{message}</strong>
          </div>
          <p className={styles.subtext}>{subtext}</p>
        </div>
        <div className={styles.infoCol}>
          <span className={styles.infoTag}>
            <Info size={12} />
            <span>Non-dismissible</span>
          </span>
        </div>
      </div>
    </div>
  );
};
