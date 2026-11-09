'use client';

import React, { useState } from 'react';
import {
  Database,
  Filter,
  Layers,
  TrendingUp,
  ShieldCheck,
  FileCheck,
  MessageSquareQuote,
  ChevronLeft,
  ChevronRight,
  Shield,
  Binary,
  CheckCircle2,
  Sparkles,
} from 'lucide-react';
import { Badge } from '../../components/ds/Badge';
import { METHOD_COPY as C, STAGE_DETAILS, type StageDetail } from './copy';
import styles from './PipelineDiagram.module.css';

const STAGE_ICONS = [
  Database,
  Filter,
  Layers,
  TrendingUp,
  ShieldCheck,
  FileCheck,
  MessageSquareQuote,
];

export function PipelineDiagram() {
  const [activeStage, setActiveStage] = useState(2); // Stage 3 (Synthetic twin) selected by default
  const stage: StageDetail = STAGE_DETAILS[activeStage];
  const isLast = activeStage === STAGE_DETAILS.length - 1;
  const StageIcon = STAGE_ICONS[activeStage];

  const prevStage = () => setActiveStage((i) => Math.max(0, i - 1));
  const nextStage = () => setActiveStage((i) => Math.min(STAGE_DETAILS.length - 1, i + 1));

  return (
    <figure className={styles.fig} aria-label={C.pipeline.alt}>
      {/* Header bar */}
      <div className={styles.headerBar}>
        <div className={styles.headerTitleGroup}>
          <span className={styles.kicker}>Audit Architecture</span>
          <h2 className={styles.headerTitle}>Seven Deterministic Stages</h2>
        </div>
        <div className={styles.legendGroup}>
          <div className={styles.legendItem}>
            <span className={styles.legendDotDeterministic} aria-hidden="true" />
            <span>Stages 1–6: Pure Deterministic Algorithms</span>
          </div>
          <div className={styles.legendItem}>
            <span className={styles.legendDotVerified} aria-hidden="true" />
            <span>Stage 7: Constrained & Audited Narration</span>
          </div>
        </div>
      </div>

      {/* Stage selector track */}
      <div className={styles.trackWrapper} role="tablist" aria-label="Pipeline stages">
        <div className={styles.stageTrack}>
          {STAGE_DETAILS.map((s, idx) => {
            const Icon = STAGE_ICONS[idx];
            const isActive = idx === activeStage;
            const isEnd = idx === STAGE_DETAILS.length - 1;

            return (
              <button
                key={s.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                aria-controls={`stage-panel-${s.id}`}
                id={`stage-tab-${s.id}`}
                tabIndex={isActive ? 0 : -1}
                className={`${styles.stageBtn} ${isActive ? styles.stageBtnActive : ''} ${isEnd ? styles.stageBtnEnd : ''}`}
                onClick={() => setActiveStage(idx)}
              >
                <div className={styles.stageTopRow}>
                  <span className={styles.stageNum}>{s.id}</span>
                  <span className={styles.stageIcon} aria-hidden="true">
                    <Icon size={16} />
                  </span>
                </div>
                <div className={styles.stageLabelGroup}>
                  <span className={styles.stageLabel}>{s.label}</span>
                  <span className={styles.stageSub}>{s.sub}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Interactive Inspector Panel */}
      <div
        id={`stage-panel-${stage.id}`}
        role="tabpanel"
        aria-labelledby={`stage-tab-${stage.id}`}
        className={styles.inspector}
      >
        <div className={styles.inspectorTop}>
          <div className={styles.inspectorTitleGroup}>
            <div className={styles.inspectorMeta}>
              <span>Stage 0{stage.id} of 07</span>
              <span>·</span>
              <span>{stage.tag}</span>
            </div>
            <h3 className={styles.inspectorTitle}>
              {stage.id}. {stage.label}: {stage.sub}
            </h3>
          </div>
          <div className={styles.inspectorBadgeGroup}>
            {stage.badge === 'deterministic' ? (
              <Badge tone="positive" variant="subtle" icon={<Binary size={12} />}>
                Deterministic Algorithm (No LLM)
              </Badge>
            ) : (
              <Badge tone="caution" variant="subtle" icon={<Sparkles size={12} />}>
                Verified Narration Only
              </Badge>
            )}
          </div>
        </div>

        <p className={styles.inspectorSummary}>{stage.summary}</p>

        {/* Details Grid */}
        <div className={styles.inspectorDetailsGrid}>
          <div className={styles.detailCard}>
            <span className={styles.detailLabel}>
              <Binary size={13} aria-hidden="true" />
              Method & Formulation
            </span>
            <div className={styles.formulaBox}>{stage.math}</div>
          </div>

          <div className={styles.detailCard}>
            <span className={styles.detailLabel}>
              <Shield size={13} aria-hidden="true" />
              Input Requirements
            </span>
            <p className={styles.detailValue}>{stage.inputs}</p>
          </div>

          <div className={styles.detailCard}>
            <span className={styles.detailLabel}>
              <FileCheck size={13} aria-hidden="true" />
              Evidence Produced
            </span>
            <p className={styles.detailValue}>{stage.outputs}</p>
          </div>
        </div>

        {/* Guarantee Banner */}
        <div className={isLast ? styles.guaranteeBoxEnd : styles.guaranteeBox} role="note">
          <CheckCircle2 size={16} aria-hidden="true" />
          <span>
            <strong>Integrity Guarantee:</strong> {stage.guarantee}
          </span>
        </div>

        {/* Navigation controls */}
        <div className={styles.inspectorNav}>
          <button
            type="button"
            className={styles.navBtn}
            onClick={prevStage}
            disabled={activeStage === 0}
            aria-label="Previous stage"
          >
            <ChevronLeft size={16} aria-hidden="true" />
            <span>Previous stage</span>
          </button>
          <span className="num" style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)' }}>
            Stage {stage.id} of {STAGE_DETAILS.length}
          </span>
          <button
            type="button"
            className={styles.navBtn}
            onClick={nextStage}
            disabled={activeStage === STAGE_DETAILS.length - 1}
            aria-label="Next stage"
          >
            <span>Next stage</span>
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </div>
      </div>

      <figcaption className={styles.cap}>
        <CheckCircle2 size={15} style={{ color: 'var(--accent)' }} aria-hidden="true" />
        <span>{C.pipeline.caption}</span>
      </figcaption>

      {/* Hidden fallback representation for screen readers */}
      <ol className={styles.srSvg}>
        {STAGE_DETAILS.map((s) => (
          <li key={s.id}>
            Stage {s.id}: {s.label} ({s.sub}) — {s.summary}
          </li>
        ))}
      </ol>
    </figure>
  );
}
