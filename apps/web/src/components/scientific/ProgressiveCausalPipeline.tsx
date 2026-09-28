'use client';

import React from 'react';
import { Shield, Satellite, GitCompare, Zap, Activity, Layers, FileCheck2, ChevronRight } from 'lucide-react';
import styles from './ProgressiveCausalPipeline.module.css';

export type CausalPipelineStage =
  | 'claim'
  | 'observed'
  | 'counterfactual'
  | 'effect'
  | 'uncertainty'
  | 'evidence'
  | 'provenance';

export interface CausalStage {
  id: CausalPipelineStage;
  label: string;
  stepNumber: string;
  value: string;
  unit?: string;
  subtext: string;
  status: 'active' | 'computed' | 'verified' | 'caution';
  icon: React.ReactNode;
}

export interface ProgressiveCausalPipelineProps {
  stages?: CausalStage[];
  activeStage?: string;
  onStageClick?: (stageId: CausalPipelineStage) => void;
  className?: string;
  claimValue?: string;
  observedValue?: string;
  counterfactualValue?: string;
  causalEffectValue?: string;
  uncertaintyValue?: string;
  /** Unit/range shown alongside `uncertaintyValue`, e.g. the indicator name. Never defaults to a fabricated interval. */
  uncertaintyUnit?: string;
  evidenceCount?: number;
  provenanceHash?: string;
}

export function ProgressiveCausalPipeline({
  stages,
  activeStage,
  onStageClick,
  className,
  claimValue,
  observedValue,
  counterfactualValue,
  causalEffectValue,
  uncertaintyValue,
  uncertaintyUnit,
  evidenceCount,
  provenanceHash,
}: ProgressiveCausalPipelineProps) {
  // Default pipeline definition if not explicitly provided
  const defaultStages: CausalStage[] = [
    {
      id: 'claim',
      stepNumber: '01',
      label: 'CLAIM',
      value: claimValue || 'VCS 902 Baseline',
      unit: '',
      subtext: 'Claimed Crediting Impact',
      status: 'active',
      icon: <Shield size={14} />,
    },
    {
      id: 'observed',
      stepNumber: '02',
      label: 'OBSERVED',
      // No fallback number: this stage has no value until a real measurement
      // supplies one. A dash is honest; a plausible-looking default is not.
      value: observedValue || '—',
      unit: 'NDVI',
      subtext: 'Sentinel-2 / Landsat',
      status: 'computed',
      icon: <Satellite size={14} />,
    },
    {
      id: 'counterfactual',
      stepNumber: '03',
      label: 'COUNTERFACTUAL',
      value: counterfactualValue || '—',
      unit: 'NDVI',
      subtext: 'Synthetic Control w_i',
      status: 'computed',
      icon: <GitCompare size={14} />,
    },
    {
      id: 'effect',
      stepNumber: '04',
      label: 'CAUSAL EFFECT',
      value: causalEffectValue || '—',
      unit: 'NDVI',
      subtext: 'Observed − Counterfactual',
      status: 'verified',
      icon: <Zap size={14} />,
    },
    {
      id: 'uncertainty',
      stepNumber: '05',
      label: 'UNCERTAINTY',
      // No fallback interval: this stage has no value until a real
      // confidence interval supplies one.
      value: uncertaintyValue || '—',
      unit: uncertaintyUnit || '',
      subtext: 'Sensitivity Envelope',
      status: 'verified',
      icon: <Activity size={14} />,
    },
    {
      id: 'evidence',
      stepNumber: '06',
      label: 'EVIDENCE',
      value: evidenceCount ? `${evidenceCount} Items` : '—',
      unit: '',
      subtext: 'Audit Proof Ledger',
      status: 'verified',
      icon: <Layers size={14} />,
    },
    {
      id: 'provenance',
      stepNumber: '07',
      label: 'PROVENANCE',
      // No fallback hash: 'SHA-256' previously appeared here regardless of
      // whether a real spec_hash existed, implying a specific algorithm and
      // a computed value neither of which were true.
      value: provenanceHash || '—',
      unit: 'Verified',
      subtext: 'Chain of Custody',
      status: 'verified',
      icon: <FileCheck2 size={14} />,
    },
  ];

  const pipelineStages = stages || defaultStages;

  return (
    <div className={`${styles.pipelineContainer} ${className || ''}`} role="region" aria-label="Progressive Causal Pipeline">
      <div className={styles.pipelineHeader}>
        <div className={styles.headerTitleGroup}>
          <span className={styles.pipelineEyebrow}>EPISTEMIC VERIFICATION ARCHITECTURE</span>
          <h3 className={styles.pipelineTitle}>Progressive Causal Revelation</h3>
        </div>
        <div className={styles.telemetryTag}>
          <span className={styles.livePulse} />
          <span>7-STAGE CAUSAL CHAIN</span>
        </div>
      </div>

      <div className={styles.stagesScrollTrack}>
        <div className={styles.stagesRow}>
          {pipelineStages.map((stage, idx) => {
            const isLast = idx === pipelineStages.length - 1;
            const isCurrent = activeStage === stage.id;

            return (
              <React.Fragment key={stage.id}>
                <button
                  type="button"
                  onClick={() => onStageClick?.(stage.id)}
                  className={`${styles.stageCard} ${styles[`status_${stage.status}`]} ${
                    isCurrent ? styles.stageActive : ''
                  }`}
                  aria-label={`Stage ${stage.stepNumber}: ${stage.label}`}
                >
                  <div className={styles.cardHeader}>
                    <span className={styles.stepNum}>{stage.stepNumber}</span>
                    <span className={styles.stageIcon}>{stage.icon}</span>
                    <span className={styles.stageLabel}>{stage.label}</span>
                  </div>

                  <div className={styles.cardBody}>
                    <div className={styles.valueRow}>
                      <span className={styles.valueText}>{stage.value}</span>
                      {stage.unit && <span className={styles.unitText}>{stage.unit}</span>}
                    </div>
                    <span className={styles.subtext}>{stage.subtext}</span>
                  </div>

                  <div className={styles.stageFooter}>
                    <span className={styles.statusPill}>{stage.status.toUpperCase()}</span>
                  </div>
                </button>

                {!isLast && (
                  <div className={styles.connector} aria-hidden="true">
                    <ChevronRight size={14} className={styles.connectorArrow} />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
}
