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
      value: observedValue || '0.642',
      unit: 'NDVI',
      subtext: 'Sentinel-2 / Landsat',
      status: 'computed',
      icon: <Satellite size={14} />,
    },
    {
      id: 'counterfactual',
      stepNumber: '03',
      label: 'COUNTERFACTUAL',
      value: counterfactualValue || '0.600',
      unit: 'NDVI',
      subtext: 'Synthetic Control w_i',
      status: 'computed',
      icon: <GitCompare size={14} />,
    },
    {
      id: 'effect',
      stepNumber: '04',
      label: 'CAUSAL EFFECT',
      value: causalEffectValue || '+0.042',
      unit: 'NDVI',
      subtext: 'Observed − Counterfactual',
      status: 'verified',
      icon: <Zap size={14} />,
    },
    {
      id: 'uncertainty',
      stepNumber: '05',
      label: 'UNCERTAINTY',
      value: uncertaintyValue || '95% CI',
      unit: '[-0.012, 0.084]',
      subtext: 'Sensitivity Envelope',
      status: 'verified',
      icon: <Activity size={14} />,
    },
    {
      id: 'evidence',
      stepNumber: '06',
      label: 'EVIDENCE',
      value: evidenceCount ? `${evidenceCount} Items` : '14 Items',
      unit: '',
      subtext: 'Audit Proof Ledger',
      status: 'verified',
      icon: <Layers size={14} />,
    },
    {
      id: 'provenance',
      stepNumber: '07',
      label: 'PROVENANCE',
      value: provenanceHash || 'SHA-256',
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
