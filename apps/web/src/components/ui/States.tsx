import React from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, HelpCircle, RefreshCw } from 'lucide-react';
import { Button } from './Button';
import { Badge } from './Badge';
import styles from './States.module.css';

/* ---------------- Loading State ---------------- */

export type PipelineStageId =
  | 'ingesting_observations'
  | 'harmonizing_sensors'
  | 'engineering_covariates'
  | 'constructing_donor_pool'
  | 'matching_controls'
  | 'fitting_counterfactual'
  | 'running_placebos'
  | 'propagating_uncertainty'
  | 'assembling_evidence'
  // Backward compatibility aliases
  | 'ingestion'
  | 'observation'
  | 'matching'
  | 'causal'
  | 'uncertainty'
  | 'verdict';

export interface LoadingStateProps {
  currentStage?: PipelineStageId;
  message?: string;
  subtext?: string;
  isSimulated?: boolean;
}

const PIPELINE_STAGES = [
  { id: 'ingesting_observations', alias: 'ingestion', label: '1. INGESTING OBSERVATIONS', desc: 'Acquiring Landsat / Sentinel-2 surface reflectance' },
  { id: 'harmonizing_sensors', alias: 'observation', label: '2. HARMONIZING SENSORS', desc: 'Cross-sensor calibration & cloud/shadow masking' },
  { id: 'engineering_covariates', alias: 'covariates', label: '3. ENGINEERING COVARIATES', desc: 'Topography, precipitation, and access proxies' },
  { id: 'constructing_donor_pool', alias: 'donor_pool', label: '4. CONSTRUCTING DONOR POOL', desc: 'Screening 42Candidate grid cells within 500km' },
  { id: 'matching_controls', alias: 'matching', label: '5. MATCHING CONTROLS', desc: 'Caliper filtering & Mahalanobis distance ranking' },
  { id: 'fitting_counterfactual', alias: 'causal', label: '6. FITTING COUNTERFACTUAL', desc: 'Simplex-constrained convex optimization' },
  { id: 'running_placebos', alias: 'placebos', label: '7. RUNNING PLACEBOS', desc: 'In-space & in-time permutation significance tests' },
  { id: 'propagating_uncertainty', alias: 'uncertainty', label: '8. PROPAGATING UNCERTAINTY', desc: 'Leave-one-out sensitivity & confidence bounds' },
  { id: 'assembling_evidence', alias: 'verdict', label: '9. ASSEMBLING EVIDENCE', desc: 'Cryptographic hashing & verdict rule evaluation' },
];

export const LoadingState: React.FC<LoadingStateProps> = ({
  currentStage = 'fitting_counterfactual',
  message = 'RUNNING CAUSAL VERIFICATION PIPELINE',
  subtext = 'Estimating counterfactual baseline and constructing placebo permutation distribution...',
  isSimulated = true,
}) => {
  const currentIdx = PIPELINE_STAGES.findIndex(
    (s) => s.id === currentStage || s.alias === currentStage
  );

  return (
    <div className={styles.loadingContainer}>
      <div className={styles.spinnerWrapper}>
        <div className={styles.pulseRing} />
        <RefreshCw size={28} className={styles.spinningIcon} />
      </div>

      <div className={styles.instrumentBadgeRow}>
        <span className={styles.instrumentTag}>INSTRUMENT TELEMETRY</span>
        {isSimulated && (
          <span className={styles.simulatedTag}>SIMULATED PIPELINE</span>
        )}
      </div>

      <h3 className={styles.loadingTitle}>{message}</h3>
      <p className={styles.loadingSubtext}>{subtext}</p>

      {/* Stage Tracker */}
      <div className={styles.stagesBox}>
        {PIPELINE_STAGES.map((stg, idx) => {
          const isDone = idx < currentIdx;
          const isCurrent = idx === currentIdx;
          return (
            <div
              key={stg.id}
              className={`${styles.stageRow} ${isCurrent ? styles.stageCurrent : ''} ${isDone ? styles.stageDone : ''}`}
            >
              <span className={styles.stageStatusIcon}>
                {isDone ? (
                  <CheckCircle2 size={14} className={styles.doneIcon} />
                ) : isCurrent ? (
                  <span className={styles.currentDot} />
                ) : (
                  <span className={styles.pendingDot} />
                )}
              </span>
              <div className={styles.stageTextCol}>
                <span className={styles.stageLabel}>{stg.label}</span>
                <span className={styles.stageDesc}>{stg.desc}</span>
              </div>
              {isCurrent && (
                <Badge tone="info" size="sm" variant="subtle">
                  PROCESSING
                </Badge>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

/* ---------------- Empty State ---------------- */

export interface EmptyStateProps {
  title: string;
  description: string;
  icon?: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  icon = <HelpCircle size={40} className={styles.emptyIcon} />,
  actionLabel,
  onAction,
}) => {
  return (
    <div className={styles.emptyContainer}>
      <div className={styles.emptyIconWrapper}>{icon}</div>
      <h3 className={styles.emptyTitle}>{title}</h3>
      <p className={styles.emptyDescription}>{description}</p>
      {actionLabel && onAction && (
        <Button variant="secondary" size="md" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
};

/* ---------------- Error State (System Malfunction) ---------------- */

export interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'System Error Encountered',
  message,
  onRetry,
}) => {
  return (
    <div className={styles.errorContainer}>
      <AlertCircle size={36} className={styles.errorIcon} />
      <h3 className={styles.errorTitle}>{title}</h3>
      <p className={styles.errorMessage}>{message}</p>
      {onRetry && (
        <Button variant="danger" size="md" onClick={onRetry}>
          Retry Operation
        </Button>
      )}
    </div>
  );
};

/* ---------------- Refusal State (Scientific Refusal) ---------------- */

export interface RefusalStateProps {
  title?: string;
  reason: string;
  remediation?: string | null;
  onBack?: () => void;
}

export const RefusalState: React.FC<RefusalStateProps> = ({
  title = 'Analysis Scientifically Refused',
  reason,
  remediation,
  onBack,
}) => {
  return (
    <div className={styles.refusalContainer}>
      <div className={styles.refusalIconWrapper}>
        <AlertTriangle size={32} className={styles.refusalIcon} />
      </div>
      <div className={styles.refusalBadgeRow}>
        <Badge tone="inconclusive" size="md" variant="solid">
          LEGITIMATE SCIENTIFIC REFUSAL
        </Badge>
      </div>
      <h3 className={styles.refusalTitle}>{title}</h3>
      <p className={styles.refusalReason}>{reason}</p>

      {remediation && (
        <div className={styles.remediationBox}>
          <strong className={styles.remediationTitle}>Remediation Guidance:</strong>
          <p className={styles.remediationText}>{remediation}</p>
        </div>
      )}

      {onBack && (
        <div className={styles.refusalActions}>
          <Button variant="secondary" size="md" onClick={onBack}>
            Return to Case Definition
          </Button>
        </div>
      )}
    </div>
  );
};
