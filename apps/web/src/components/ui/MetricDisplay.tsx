import React from 'react';
import { Confidence } from '../../lib/types';
import { formatEvidenceValue, formatConfidenceInterval } from '../../lib/formatters';
import { Tooltip } from './Tooltip';
import { Badge } from './Badge';
import { HelpCircle } from 'lucide-react';
import styles from './MetricDisplay.module.css';

export interface MetricDisplayProps {
  label: string;
  value: number | string | boolean;
  unit?: string | null;
  confidence?: Confidence | null;
  delta?: {
    value: number;
    unit?: string;
    isPositiveGood?: boolean;
    label?: string;
  };
  tooltip?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const MetricDisplay: React.FC<MetricDisplayProps> = ({
  label,
  value,
  unit,
  confidence,
  delta,
  tooltip,
  size = 'md',
  className = '',
}) => {
  const formattedVal = formatEvidenceValue(value, null);
  const confidenceStr = formatConfidenceInterval(confidence ?? null, unit || undefined);

  return (
    <div className={`${styles.container} ${styles[size]} ${className}`}>
      <div className={styles.labelRow}>
        <span className={styles.label}>{label}</span>
        {tooltip && (
          <Tooltip content={tooltip}>
            <HelpCircle size={13} className={styles.helpIcon} />
          </Tooltip>
        )}
      </div>

      <div className={styles.valueRow}>
        <span className={styles.value}>{formattedVal}</span>
        {unit && <span className={styles.unit}>{unit}</span>}
      </div>

      {confidence && (
        <div className={styles.confidenceRow}>
          <Badge tone="neutral" size="sm" variant="subtle">
            {confidenceStr}
          </Badge>
        </div>
      )}

      {delta && (
        <div className={styles.deltaRow}>
          <span
            className={`${styles.delta} ${
              delta.value > 0
                ? delta.isPositiveGood !== false ? styles.positive : styles.caution
                : delta.isPositiveGood !== false ? styles.caution : styles.positive
            }`}
          >
            {delta.value > 0 ? '+' : ''}
            {delta.value.toFixed(3)} {delta.unit || unit}
          </span>
          {delta.label && <span className={styles.deltaLabel}>({delta.label})</span>}
        </div>
      )}
    </div>
  );
};
