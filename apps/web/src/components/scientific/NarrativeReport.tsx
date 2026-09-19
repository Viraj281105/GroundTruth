'use client';

import React from 'react';
import { Badge } from '../ui/Badge';
import { FileText, ShieldCheck, AlertCircle } from 'lucide-react';
import styles from './NarrativeReport.module.css';

export interface NarrativeReportProps {
  markdown?: string | null;
  generator?: string | null;
  className?: string;
}

export const NarrativeReport: React.FC<NarrativeReportProps> = ({
  markdown,
  generator = 'deterministic-renderer',
  className = '',
}) => {
  if (!markdown) {
    return (
      <div className={styles.empty}>
        No narrative report was requested or generated for this run.
      </div>
    );
  }

  const isGenAI = generator?.toLowerCase().includes('genai');

  return (
    <div className={`${styles.container} ${className}`}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <FileText size={18} className={styles.icon} />
          <h4 className={styles.title}>Verification Screening Narrative</h4>
        </div>
        <div className={styles.headerRight}>
          <Badge tone={isGenAI ? 'info' : 'positive'} size="sm" variant="subtle">
            GENERATOR: {generator ? generator.toUpperCase() : 'DETERMINISTIC'}
          </Badge>
          <Badge tone="neutral" size="sm" variant="outline">
            NUMERICALLY GROUNDED
          </Badge>
        </div>
      </div>

      {/* Grounding statement */}
      <div className={styles.groundingNotice}>
        <ShieldCheck size={16} className={styles.groundingIcon} />
        <p className={styles.groundingText}>
          <strong>Grounding Guarantee:</strong> Every numerical claim in this narrative was verified against the immutable evidence bundle. Hallucinated figures, ungrounded causal claims, or allegations of fraud are automatically rejected by the grounding layer.
        </p>
      </div>

      {/* Report Markdown Content */}
      <div className={styles.markdownContent}>
        <pre className={styles.renderedText}>{markdown}</pre>
      </div>
    </div>
  );
};
