import React from 'react';
import { VerdictLabel, VerificationVerdict } from '../../lib/types';
import { formatDivergenceRatio } from '../../lib/formatters';
import { Badge } from './Badge';
import {
  ShieldCheck,
  AlertCircle,
  HelpCircle,
  AlertTriangle,
  FileText,
  Scale,
  Activity,
  CheckCircle2,
} from 'lucide-react';
import styles from './VerdictCard.module.css';

export interface VerdictCardProps {
  verdict: VerificationVerdict;
  caseName?: string;
  className?: string;
}

const VERDICT_CONFIG: Record<
  VerdictLabel,
  {
    title: string;
    tone: 'positive' | 'caution' | 'inconclusive' | 'neutral';
    icon: React.ReactNode;
    tagline: string;
    bannerLabel: string;
  }
> = {
  consistent_with_claim: {
    title: 'Consistent with Developer Claim',
    tone: 'positive',
    icon: <ShieldCheck size={28} />,
    tagline: 'Independent causal estimate aligns with the registered baseline within screening tolerance (±30%).',
    bannerLabel: 'SCREENING VERDICT: CONSISTENT',
  },
  divergent_from_claim: {
    title: 'Divergent from Developer Claim',
    tone: 'caution',
    icon: <AlertTriangle size={28} />,
    tagline: 'Independent causal estimate diverges beyond screening tolerance (±30%). Warrants accredited field review.',
    bannerLabel: 'SCREENING VERDICT: DIVERGENT (TRIGGERS AUDIT)',
  },
  inconclusive: {
    title: 'Inconclusive Screening Outcome',
    tone: 'inconclusive',
    icon: <HelpCircle size={28} />,
    tagline: 'A robust incremental effect was estimated, but methodological or unit constraints prevent comparison to the claim.',
    bannerLabel: 'SCREENING VERDICT: INCONCLUSIVE (LEGITIMATE STATE)',
  },
  not_assessed: {
    title: 'Not Assessed',
    tone: 'neutral',
    icon: <AlertCircle size={28} />,
    tagline: 'This project has not completed an evaluation pipeline run.',
    bannerLabel: 'STATUS: NOT ASSESSED',
  },
};

function categorizeCaveat(caveat: string): { tag: string; tone: 'simulated' | 'caution' | 'info' | 'neutral' } {
  const lower = caveat.toLowerCase();
  if (lower.includes('simulated') || lower.includes('synthetic')) {
    return { tag: 'DATA MODE', tone: 'simulated' };
  }
  if (lower.includes('ndvi') || lower.includes('spectral') || lower.includes('carbon')) {
    return { tag: 'UNITS GUARD', tone: 'info' };
  }
  if (lower.includes('fraud') || lower.includes('intent') || lower.includes('review')) {
    return { tag: 'SCREENING ONLY', tone: 'caution' };
  }
  if (lower.includes('causal') || lower.includes('assumptions') || lower.includes('observed')) {
    return { tag: 'CAUSAL IDENTIFICATION', tone: 'neutral' };
  }
  return { tag: 'METHODOLOGY', tone: 'neutral' };
}

export const VerdictCard: React.FC<VerdictCardProps> = ({
  verdict,
  caseName,
  className = '',
}) => {
  const config = VERDICT_CONFIG[verdict.label] || VERDICT_CONFIG.inconclusive;
  const hasDivergence = verdict.divergence_ratio !== null && verdict.divergence_ratio !== undefined;

  return (
    <div className={`${styles.card} ${styles[config.tone]} ${className}`}>
      {/* Top row: Verdict Header */}
      <div className={styles.header}>
        <div className={styles.iconContainer}>{config.icon}</div>
        <div className={styles.headerText}>
          <div className={styles.metaRow}>
            <Badge tone={config.tone} size="sm" variant="solid">
              {config.bannerLabel}
            </Badge>
            {caseName && <span className={styles.caseName}>{caseName}</span>}
          </div>
          <h2 className={styles.title}>{config.title}</h2>
          <p className={styles.tagline}>{config.tagline}</p>
        </div>

        {hasDivergence && (
          <div className={styles.divergenceBox}>
            <span className={styles.divergenceLabel}>DIVERGENCE RATIO</span>
            <span className={styles.divergenceValue}>
              {formatDivergenceRatio(verdict.divergence_ratio)}
            </span>
            <span className={styles.divergenceThreshold}>Threshold: ±30%</span>
          </div>
        )}
      </div>

      {/* Divergence Tolerance Visual Gauge (When ratio is provided) */}
      {hasDivergence && (
        <div className={styles.gaugeContainer}>
          <div className={styles.gaugeHeader}>
            <span className={styles.gaugeTitle}>Screening Tolerance Gauge (±30% Bound)</span>
            <span className={styles.gaugeRatio}>
              {verdict.divergence_ratio! < 0.7
                ? 'Divergence: Below registered claim'
                : verdict.divergence_ratio! > 1.3
                ? 'Divergence: Above registered claim'
                : 'Within ±30% tolerance band'}
            </span>
          </div>
          <div className={styles.gaugeTrack}>
            {/* 0.70x to 1.30x Tolerance Zone */}
            <div className={styles.gaugeToleranceZone} style={{ left: '35%', width: '30%' }}>
              <span className={styles.toleranceLabel}>Tolerance Band (0.7x – 1.3x)</span>
            </div>
            {/* Developer Claim Target (1.0x) */}
            <div className={styles.gaugeTargetMarker} style={{ left: '50%' }}>
              <span className={styles.markerLabel}>Claim (1.0x)</span>
            </div>
            {/* Independent Estimate Marker */}
            <div
              className={styles.gaugeEstimateMarker}
              style={{
                left: `${Math.min(Math.max((verdict.divergence_ratio! / 2) * 100, 5), 95)}%`,
              }}
            >
              <div className={styles.estimatePin} />
              <span className={styles.estimateLabel}>
                Estimate ({verdict.divergence_ratio!.toFixed(2)}x)
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Special Inconclusive Distinction Notice */}
      {verdict.label === 'inconclusive' && (
        <div className={styles.inconclusiveCallout}>
          <Scale size={18} className={styles.inconclusiveIcon} />
          <div className={styles.inconclusiveText}>
            <strong>Why is this screening inconclusive?</strong>
            <p>
              The causal pipeline verified a statistically distinguishable incremental effect on the observed satellite index, but the developer&apos;s registered claim is denominated in carbon mass (tCO2e). Enforcing contract rule <code style={{ color: 'var(--gt-accent-cyan)' }}>assert_not_index_to_carbon</code>, the system refuses to fabricate a direct conversion until an accredited biomass allometry model is connected.
            </p>
          </div>
        </div>
      )}

      {/* Analytical Rationale */}
      <div className={styles.rationaleBox}>
        <h4 className={styles.sectionHeading}>Analytical Rationale</h4>
        <p className={styles.rationaleText}>{verdict.rationale}</p>
      </div>

      {/* NON-COLLAPSIBLE CAVEATS (Strictly enforced UI Rule 4) */}
      <div className={styles.caveatsBox}>
        <div className={styles.caveatsHeader}>
          <FileText size={15} className={styles.caveatIcon} />
          <h4 className={styles.caveatsTitle}>
            Mandatory Methodological Caveats (Non-collapsed)
          </h4>
        </div>
        <div className={styles.caveatsList}>
          {verdict.caveats.map((caveat, idx) => {
            const cat = categorizeCaveat(caveat);
            return (
              <div key={idx} className={styles.caveatItem}>
                <Badge tone={cat.tone} size="sm" variant="subtle" className={styles.caveatBadge}>
                  {cat.tag}
                </Badge>
                <p className={styles.caveatText}>{caveat}</p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
