import React from 'react';
import styles from './StatusIndicator.module.css';

export type StatusType =
  | 'completed'
  | 'running'
  | 'queued'
  | 'refused'
  | 'error'
  | 'scaffolded'
  | 'data-wired'
  | 'analysed';

export interface StatusIndicatorProps {
  status: StatusType;
  label?: string;
  size?: 'sm' | 'md';
  pulse?: boolean;
  className?: string;
}

const DEFAULT_LABELS: Record<StatusType, string> = {
  completed: 'Completed',
  running: 'Running',
  queued: 'Queued',
  refused: 'Scientifically Refused',
  error: 'System Error',
  scaffolded: 'Scaffolded',
  'data-wired': 'Data Wired',
  analysed: 'Analysed',
};

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  status,
  label,
  size = 'md',
  pulse,
  className = '',
}) => {
  const displayLabel = label || DEFAULT_LABELS[status] || status;
  const shouldPulse = pulse ?? (status === 'running' || status === 'queued');

  return (
    <div className={`${styles.wrapper} ${styles[size]} ${className}`}>
      <span
        className={`${styles.dot} ${styles[status]} ${shouldPulse ? styles.pulse : ''}`}
        aria-hidden="true"
      />
      <span className={`${styles.label} ${styles[status + 'Text']}`}>
        {displayLabel}
      </span>
    </div>
  );
};
