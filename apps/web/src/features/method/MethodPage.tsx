'use client';

import React, { useState, useMemo } from 'react';
import Link from 'next/link';
import {
  Scale,
  TrendingUp,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Lock,
  Search,
  X,
  Link2,
  Check,
  BookOpen,
  Binary,
  ArrowRight,
  ShieldCheck,
  Layers,
  Sparkles,
  AlertTriangle,
  ExternalLink,
  Cpu,
} from 'lucide-react';
import { Chip } from '../../components/ds/Chip';
import { Badge } from '../../components/ds/Badge';
import { LinkButton } from '../../components/ds/Button';
import { GLOSSARY_TERMS, glossary } from '../../lib/glossary';
import { PipelineDiagram } from './PipelineDiagram';
import {
  METHOD_COPY as C,
  METHODOLOGICAL_NOTES,
  GLOSSARY_CATEGORIES,
  TERM_CATEGORY_MAP,
} from './copy';
import styles from './MethodPage.module.css';

/* =========================================================================
 * STEP VISUAL ARTWORK (Interactive SVG illustrations)
 * ========================================================================= */

function StepOneArt() {
  const donorPoints = [
    [30, 45],
    [60, 95],
    [45, 145],
    [85, 175],
    [115, 65],
    [135, 125],
  ];

  return (
    <svg
      viewBox="0 0 320 190"
      className={styles.stepSvg}
      role="img"
      aria-label="Untreated donor land areas weighted into a synthetic twin with SUTVA exclusion belt"
    >
      <defs>
        <radialGradient id="sutvaGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* SUTVA exclusion buffer ring */}
      <circle
        cx="255"
        cy="95"
        r="44"
        fill="url(#sutvaGlow)"
        stroke="var(--border-strong)"
        strokeDasharray="3 3"
      />
      <text
        x="255"
        y="92"
        textAnchor="middle"
        fill="var(--text-muted)"
        fontSize="9"
        fontWeight="600"
      >
        PROJECT BOUNDARY
      </text>
      <text
        x="255"
        y="104"
        textAnchor="middle"
        fill="var(--sim-text)"
        fontSize="8"
        fontWeight="600"
      >
        SUTVA Exclusion Belt
      </text>

      {/* Untreated donor units and convergence lines */}
      {donorPoints.map(([x, y], i) => (
        <g key={i}>
          <path
            d={`M${x} ${y} C130 ${y} 150 95 200 95`}
            fill="none"
            stroke="var(--border-default)"
            strokeWidth="1.5"
            strokeDasharray="2 3"
          />
          <circle
            cx={x}
            cy={y}
            r="5"
            fill="var(--surface-raised)"
            stroke="var(--border-strong)"
            strokeWidth="1.5"
          />
          <circle cx={x} cy={y} r="2.5" fill="var(--chart-b)" />
        </g>
      ))}

      {/* Synthetic twin blended line */}
      <path
        d="M200 95 C225 95 240 75 295 65"
        fill="none"
        stroke="var(--gold)"
        strokeWidth="3"
        strokeLinecap="round"
      />

      <text x="30" y="24" fill="var(--text-muted)" fontSize="10" fontWeight="600">
        Untreated Donor Candidates
      </text>
      <text x="215" y="50" fill="var(--gold)" fontSize="10" fontWeight="700">
        Synthetic Twin (w*)
      </text>
    </svg>
  );
}

function StepTwoArt() {
  return (
    <svg
      viewBox="0 0 320 190"
      className={styles.stepSvg}
      role="img"
      aria-label="Observed project trajectory and synthetic twin diverging post-intervention"
    >
      {/* Axes */}
      <path d="M25 165 H295" stroke="var(--border-default)" strokeWidth="1.5" />
      <path d="M25 25 V165" stroke="var(--border-default)" strokeWidth="1.5" />

      {/* Intervention line */}
      <line
        x1="135"
        y1="25"
        x2="135"
        y2="165"
        stroke="var(--text-muted)"
        strokeWidth="1.5"
        strokeDasharray="3 3"
      />
      <text x="139" y="36" fill="var(--text-muted)" fontSize="9" fontWeight="600">
        T₀ (Project Start)
      </text>

      {/* Pre-period matching path */}
      <path
        d="M25 125 C60 122 95 116 135 114"
        fill="none"
        stroke="var(--border-strong)"
        strokeWidth="2.5"
        strokeDasharray="1 1"
      />

      {/* Shaded counterfactual effect gap */}
      <path
        d="M135 114 C175 112 225 106 290 100 L290 50 C225 62 175 80 135 114 Z"
        fill="var(--accent-soft)"
        opacity="0.75"
      />

      {/* Post-period synthetic counterfactual */}
      <path
        d="M135 114 C175 112 225 106 290 100"
        fill="none"
        stroke="var(--gold)"
        strokeWidth="3"
        strokeLinecap="round"
      />

      {/* Post-period observed treated */}
      <path
        d="M135 114 C175 80 225 62 290 50"
        fill="none"
        stroke="var(--accent)"
        strokeWidth="3"
        strokeLinecap="round"
      />

      <text x="40" y="142" fill="var(--text-muted)" fontSize="9">
        Pre-period match
      </text>
      <text x="230" y="42" fill="var(--accent)" fontSize="10" fontWeight="700">
        Observed Y₁
      </text>
      <text x="230" y="118" fill="var(--gold)" fontSize="10" fontWeight="700">
        Synthetic Ŷ₀
      </text>
      <text x="210" y="78" fill="var(--accent-strong)" fontSize="9" fontWeight="600">
        Estimated Gap τ̂
      </text>
    </svg>
  );
}

function StepThreeArt() {
  const bars = [8, 16, 26, 44, 68, 44, 26, 14, 8, 4];

  return (
    <svg
      viewBox="0 0 320 190"
      className={styles.stepSvg}
      role="img"
      aria-label="Distribution of placebo effects with the observed effect far on the right"
    >
      <path d="M25 165 H295" stroke="var(--border-default)" strokeWidth="1.5" />

      {/* Placebo bars */}
      {bars.map((h, i) => (
        <rect
          key={i}
          x={35 + i * 20}
          y={165 - h * 1.8}
          width="15"
          height={h * 1.8}
          rx="2"
          fill="var(--surface-sunken)"
          stroke="var(--border-default)"
          strokeWidth="1"
        />
      ))}

      {/* Observed effect bar far to the right */}
      <rect
        x="255"
        y={165 - 125}
        width="16"
        height="125"
        rx="2"
        fill="var(--accent)"
      />

      {/* P-value boundary line */}
      <line
        x1="245"
        y1="30"
        x2="245"
        y2="165"
        stroke="var(--danger-text)"
        strokeWidth="1.5"
        strokeDasharray="2 2"
      />

      <text x="35" y="32" fill="var(--text-muted)" fontSize="9" fontWeight="600">
        Placebo Distribution (H₀)
      </text>
      <text x="230" y="22" fill="var(--accent)" fontSize="10" fontWeight="700">
        Observed τ̂
      </text>
      <text x="175" y="50" fill="var(--danger-text)" fontSize="8">
        Floor: 1/(N+1)
      </text>
    </svg>
  );
}

/* =========================================================================
 * MAIN METHOD PAGE COMPONENT
 * ========================================================================= */

export function MethodPage() {
  // Glossary state
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [viewMode, setViewMode] = useState<'both' | 'plain' | 'technical'>('both');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Filter glossary entries
  const filteredTerms = useMemo(() => {
    return GLOSSARY_TERMS.filter((id) => {
      const e = glossary(id);
      if (!e) return false;

      // Category filter
      if (selectedCategory !== 'all') {
        const cat = TERM_CATEGORY_MAP[id];
        if (cat !== selectedCategory) return false;
      }

      // Search query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesLabel = e.label.toLowerCase().includes(q);
        const matchesPlain = e.plain.toLowerCase().includes(q);
        const matchesTechnical = e.technical.toLowerCase().includes(q);
        const matchesId = id.toLowerCase().includes(q);
        return matchesLabel || matchesPlain || matchesTechnical || matchesId;
      }

      return true;
    });
  }, [searchQuery, selectedCategory]);

  const copyAnchor = (id: string) => {
    if (typeof window !== 'undefined') {
      const url = `${window.location.origin}${window.location.pathname}#${id}`;
      if (navigator.clipboard) {
        navigator.clipboard
          .writeText(url)
          .then(() => {
            setCopiedId(id);
            setTimeout(() => setCopiedId(null), 2000);
          })
          .catch(() => {});
      }
    }
  };

  return (
    <div className={`gt-container ${styles.page}`}>
      {/* 1. HERO SECTION */}
      <header className={styles.hero}>
        <div className={styles.heroEyebrow}>
          <span className={styles.heroBadge}>
            <Binary size={12} aria-hidden="true" />
            Deterministic Causal Engine · 7-Stage Audit Pipeline
          </span>
        </div>

        <h1 className={styles.heroTitle}>{C.title}</h1>
        <p className={styles.heroLead}>{C.intro}</p>

        <p className={styles.heroContext}>
          GroundTruth replaces naive before-and-after satellite observation with convex-weighted
          counterfactual modeling, permutation stress-testing, and cryptographically verified
          evidence bundles.
        </p>

        {/* Highlight Key Metrics Strip */}
        <div className={styles.metricsStrip}>
          <div className={styles.metricCard}>
            <span className={`${styles.metricNum} num`}>7</span>
            <span className={styles.metricLabel}>Pipeline Stages</span>
            <span className={styles.metricHint}>Stages 1–6 deterministic numerical algorithms</span>
          </div>
          <div className={styles.metricCard}>
            <span className={`${styles.metricNum} num`}>Σ wᵢ = 1</span>
            <span className={styles.metricLabel}>Simplex Convex Hull</span>
            <span className={styles.metricHint}>Interpolates comparable donors without extrapolation</span>
          </div>
          <div className={styles.metricCard}>
            <span className={`${styles.metricNum} num`}>1 / (N + 1)</span>
            <span className={styles.metricLabel}>Permutation P-Value Floor</span>
            <span className={styles.metricHint}>Finite-sample significance over untreated placebos</span>
          </div>
          <div className={styles.metricCard}>
            <span className={`${styles.metricNum} num`}>100%</span>
            <span className={styles.metricLabel}>Evidence Provenance</span>
            <span className={styles.metricHint}>Every number traced to verifiable data hashes</span>
          </div>
        </div>
      </header>

      {/* 2. STICKY QUICK JUMP NAVIGATION */}
      <nav className={styles.quickNavContainer} aria-label="Page sections">
        <div className={styles.quickNav}>
          <a href="#pipeline" className={styles.quickNavLink}>
            <span className={styles.quickNavNum}>01</span>
            <span>Pipeline Architecture</span>
          </a>
          <a href="#steps" className={styles.quickNavLink}>
            <span className={styles.quickNavNum}>02</span>
            <span>Three Steps</span>
          </a>
          <a href="#ai" className={styles.quickNavLink}>
            <span className={styles.quickNavNum}>03</span>
            <span>AI Boundaries</span>
          </a>
          <a href="#assumptions" className={styles.quickNavLink}>
            <span className={styles.quickNavNum}>04</span>
            <span>Assumptions</span>
          </a>
          <a href="#limits" className={styles.quickNavLink}>
            <span className={styles.quickNavNum}>05</span>
            <span>Limits & Transparency</span>
          </a>
          <a href="#glossary" className={styles.quickNavLink}>
            <span className={styles.quickNavNum}>06</span>
            <span>Interactive Glossary</span>
          </a>
        </div>
      </nav>

      {/* 3. PIPELINE VISUALIZER SECTION */}
      <section id="pipeline" className={styles.section} aria-labelledby="pipeline-heading">
        <div className={styles.sectionHeader}>
          <span className={styles.kicker}>Stage Architecture</span>
          <h2 id="pipeline-heading" className={styles.h2}>
            The End-to-End Verification Pipeline
          </h2>
          <p className={styles.lead}>
            Click any stage below to inspect its mathematical formulation, data inputs, and
            integrity guarantees.
          </p>
        </div>

        <PipelineDiagram />
      </section>

      {/* 4. THREE-STEP METHOD SECTION */}
      <section id="steps" className={styles.section} aria-labelledby="steps-heading">
        <div className={styles.sectionHeader}>
          <span className={styles.kicker}>Core Methodology</span>
          <h2 id="steps-heading" className={styles.h2}>
            {C.steps.title}
          </h2>
          <p className={styles.lead}>
            How an assertion from a project developer is converted into an independent, audit-ready
            causal estimate.
          </p>
        </div>

        <div className={styles.stepsGrid}>
          {/* Step 1 */}
          <article className={styles.stepCard}>
            <div className={styles.stepTop}>
              <span className={styles.stepNumBadge}>01</span>
              <Badge tone="positive" variant="outline">
                Donor Matching
              </Badge>
            </div>
            <div className={styles.stepArtContainer}>
              <StepOneArt />
            </div>
            <h3 className={styles.stepHeading}>{C.steps.items[0].heading}</h3>
            <p className={styles.stepBody}>{C.steps.items[0].body}</p>
            <div className={styles.stepTags}>
              <span className={styles.stepTag}>SUTVA Eligibility</span>
              <span className={styles.stepTag}>Convex Simplex Hull</span>
              <span className={styles.stepTag}>Pre-Period RMSPE</span>
            </div>
          </article>

          {/* Step 2 */}
          <article className={styles.stepCard}>
            <div className={styles.stepTop}>
              <span className={styles.stepNumBadge}>02</span>
              <Badge tone="caution" variant="outline">
                Counterfactual
              </Badge>
            </div>
            <div className={styles.stepArtContainer}>
              <StepTwoArt />
            </div>
            <h3 className={styles.stepHeading}>{C.steps.items[1].heading}</h3>
            <p className={styles.stepBody}>{C.steps.items[1].body}</p>
            <div className={styles.stepTags}>
              <span className={styles.stepTag}>Post-Period Trajectory</span>
              <span className={styles.stepTag}>Effect Gap τ̂</span>
              <span className={styles.stepTag}>Sensitivity Envelopes</span>
            </div>
          </article>

          {/* Step 3 */}
          <article className={styles.stepCard}>
            <div className={styles.stepTop}>
              <span className={styles.stepNumBadge}>03</span>
              <Badge tone="info" variant="outline">
                Permutation
              </Badge>
            </div>
            <div className={styles.stepArtContainer}>
              <StepThreeArt />
            </div>
            <h3 className={styles.stepHeading}>{C.steps.items[2].heading}</h3>
            <p className={styles.stepBody}>{C.steps.items[2].body}</p>
            <div className={styles.stepTags}>
              <span className={styles.stepTag}>In-Space Placebos</span>
              <span className={styles.stepTag}>Leave-One-Out Refits</span>
              <span className={styles.stepTag}>Floor: 1/(N+1)</span>
            </div>
          </article>
        </div>
      </section>

      {/* 5. AI BOUNDARIES SECTION */}
      <section id="ai" className={styles.section} aria-labelledby="ai-heading">
        <div className={styles.sectionHeader}>
          <span className={styles.kicker}>System Integrity & Guardrails</span>
          <h2 id="ai-heading" className={styles.h2}>
            {C.ai.title}
          </h2>
          <p className={styles.lead}>
            GroundTruth enforces strict architectural boundaries so that language models cannot
            influence causal estimates, weights, or verdicts.
          </p>
        </div>

        <div className={styles.aiGrid}>
          {/* Card: What it does */}
          <div className={`${styles.aiCard} ${styles.aiCardDo}`}>
            <div className={styles.aiCardHeader}>
              <h3 className={styles.aiCardTitle}>
                <CheckCircle2 size={20} className={styles.aiIconDo} aria-hidden="true" />
                <span>What the AI does</span>
              </h3>
              <Badge tone="positive">Verified & Constrained</Badge>
            </div>
            <ul className={styles.aiList}>
              {C.ai.does.map((t) => (
                <li key={t} className={styles.aiItem}>
                  <CheckCircle2 size={16} className={styles.aiIconDo} aria-hidden="true" />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Card: What it does NOT do */}
          <div className={`${styles.aiCard} ${styles.aiCardDont}`}>
            <div className={styles.aiCardHeader}>
              <h3 className={styles.aiCardTitle}>
                <XCircle size={20} className={styles.aiIconDont} aria-hidden="true" />
                <span>What the AI does not do</span>
              </h3>
              <Badge tone="error">Strictly Prohibited</Badge>
            </div>
            <ul className={styles.aiList}>
              {C.ai.doesNot.map((t) => (
                <li key={t} className={styles.aiItem}>
                  <XCircle size={16} className={styles.aiIconDont} aria-hidden="true" />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Status Callout Banner */}
        <div className={styles.aiStatusNote} role="note">
          <Lock size={18} className={styles.aiStatusIcon} aria-hidden="true" />
          <div>
            <strong>Operational Status: </strong>
            <span>{C.ai.status}</span>
          </div>
        </div>
      </section>

      {/* 6. ASSUMPTIONS & SCIENTIFIC FOUNDATIONS SECTION */}
      <section id="assumptions" className={styles.section} aria-labelledby="assumptions-heading">
        <div className={styles.sectionHeader}>
          <span className={styles.kicker}>Econometric Identification</span>
          <h2 id="assumptions-heading" className={styles.h2}>
            {C.assumptions.title}
          </h2>
          <p className={styles.lead}>
            Causal inference requires explicit conditions. If an assumption is violated, the
            engine issues diagnostic flags or refuses estimation.
          </p>
        </div>

        <div className={styles.assumptionsGrid}>
          {/* Assumption 1: SUTVA */}
          <article className={styles.assumptionCard}>
            <div className={styles.assumptionTop}>
              <Badge tone="positive" variant="outline">
                SUTVA
              </Badge>
              <span className="num" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                Rule 01
              </span>
            </div>
            <h3 className={styles.assumptionTitle}>No Spillover to Comparison Land</h3>
            <p className={styles.assumptionBody}>{C.assumptions.items[0]}</p>
            <span className={styles.assumptionPill}>
              {METHODOLOGICAL_NOTES.sutvaDonorEligibility}
            </span>
          </article>

          {/* Assumption 2: Convex Hull & Identifiability */}
          <article className={styles.assumptionCard}>
            <div className={styles.assumptionTop}>
              <Badge tone="caution" variant="outline">
                Convex Hull
              </Badge>
              <span className="num" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                Rule 02
              </span>
            </div>
            <h3 className={styles.assumptionTitle}>Weight Identification & Degrees of Freedom</h3>
            <p className={styles.assumptionBody}>{C.assumptions.items[1]}</p>
            <span className={styles.assumptionPill}>
              {METHODOLOGICAL_NOTES.weightIdentification}
            </span>
          </article>

          {/* Assumption 3: Spectral Continuity */}
          <article className={styles.assumptionCard}>
            <div className={styles.assumptionTop}>
              <Badge tone="info" variant="outline">
                Remote Sensing
              </Badge>
              <span className="num" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                Rule 03
              </span>
            </div>
            <h3 className={styles.assumptionTitle}>Radiometric & Sensor Continuity</h3>
            <p className={styles.assumptionBody}>{C.assumptions.items[2]}</p>
            <span className={styles.assumptionPill}>
              Surface reflectance harmonized across Landsat and Sentinel sensors
            </span>
          </article>

          {/* Assumption 4: Covariate Balance */}
          <article className={styles.assumptionCard}>
            <div className={styles.assumptionTop}>
              <Badge tone="neutral" variant="outline">
                Covariate Balance
              </Badge>
              <span className="num" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                Rule 04
              </span>
            </div>
            <h3 className={styles.assumptionTitle}>Static Baseline Balance (SMD)</h3>
            <p className={styles.assumptionBody}>{C.assumptions.items[3]}</p>
            <span className={styles.assumptionPill}>
              {METHODOLOGICAL_NOTES.smdCovariateBalance}
            </span>
          </article>
        </div>
      </section>

      {/* 7. LIMITS & HONEST STATUS SECTION */}
      <section id="limits" className={styles.section} aria-labelledby="limits-heading">
        <div className={styles.sectionHeader}>
          <span className={styles.kicker}>Transparency & Boundaries</span>
          <h2 id="limits-heading" className={styles.h2}>
            {C.limits.title}
          </h2>
          <p className={styles.lead}>
            What GroundTruth can and cannot say. We communicate limitations openly to avoid false
            precision.
          </p>
        </div>

        <div className={styles.limitsGrid}>
          {/* Limit 1: Simulated data */}
          <div className={styles.limitCard}>
            <div className={styles.limitHeader}>
              <Chip tone="sim" dot>
                SIMULATED DATA
              </Chip>
              <span className="num" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                Notice 1
              </span>
            </div>
            <h3 className={styles.limitTitle}>Deterministic Synthetic Fixtures</h3>
            <p className={styles.limitBody}>{C.limits.items[0]}</p>
          </div>

          {/* Limit 2: Refusal */}
          <div className={styles.limitCard}>
            <div className={styles.limitHeader}>
              <Badge tone="caution">REFUSAL POLICY</Badge>
              <span className="num" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                Notice 2
              </span>
            </div>
            <h3 className={styles.limitTitle}>Refusal Rather Than Imputation</h3>
            <p className={styles.limitBody}>{C.limits.items[1]}</p>
          </div>

          {/* Limit 3: NDVI is not carbon */}
          <div className={styles.limitCard}>
            <div className={styles.limitHeader}>
              <Badge tone="error">NOT CALIBRATED</Badge>
              <span className="num" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                Notice 3
              </span>
            </div>
            <h3 className={styles.limitTitle}>Reflectance Ratios Are Not Carbon</h3>
            <p className={styles.limitBody}>{C.limits.items[2]}</p>
          </div>

          {/* Limit 4: P-value floor */}
          <div className={styles.limitCard}>
            <div className={styles.limitHeader}>
              <Badge tone="info">MATHEMATICAL FLOOR</Badge>
              <span className="num" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                Notice 4
              </span>
            </div>
            <h3 className={styles.limitTitle}>Permutation Floor: 1 / (N + 1)</h3>
            <p className={styles.limitBody}>{C.limits.items[3]}</p>
          </div>

          {/* Limit 5: Screening signal */}
          <div className={styles.limitCard}>
            <div className={styles.limitHeader}>
              <Badge tone="neutral">DECISION SUPPORT</Badge>
              <span className="num" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                Notice 5
              </span>
            </div>
            <h3 className={styles.limitTitle}>Screening Signal, Not Legal Finding</h3>
            <p className={styles.limitBody}>{C.limits.items[4]}</p>
          </div>
        </div>
      </section>

      {/* 8. INTERACTIVE GLOSSARY SECTION */}
      <section id="glossary" className={styles.section} aria-labelledby="glossary-heading">
        <div className={styles.sectionHeader}>
          <span className={styles.kicker}>Terminology & Rigor</span>
          <h2 id="glossary-heading" className={styles.h2}>
            {C.glossary.title}
          </h2>
          <p className={styles.lead}>{C.glossary.intro}</p>
        </div>

        {/* Interactive Glossary Controls */}
        <div className={styles.glossaryControls}>
          <div className={styles.searchRow}>
            <div className={styles.searchBox}>
              <Search size={16} className={styles.searchIcon} aria-hidden="true" />
              <input
                type="text"
                className={styles.searchInput}
                placeholder="Search glossary terms (e.g. counterfactual, SUTVA, p-value)..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Filter glossary terms"
              />
              {searchQuery && (
                <button
                  type="button"
                  className={styles.clearSearchBtn}
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear search query"
                >
                  <X size={15} />
                </button>
              )}
            </div>

            <div className={styles.viewModeGroup} role="group" aria-label="Glossary view mode">
              <button
                type="button"
                className={`${styles.viewModeBtn} ${viewMode === 'both' ? styles.viewModeBtnActive : ''}`}
                onClick={() => setViewMode('both')}
              >
                Dual View
              </button>
              <button
                type="button"
                className={`${styles.viewModeBtn} ${viewMode === 'plain' ? styles.viewModeBtnActive : ''}`}
                onClick={() => setViewMode('plain')}
              >
                Plain Language
              </button>
              <button
                type="button"
                className={`${styles.viewModeBtn} ${viewMode === 'technical' ? styles.viewModeBtnActive : ''}`}
                onClick={() => setViewMode('technical')}
              >
                Technical
              </button>
            </div>
          </div>

          {/* Category filter pills */}
          <div className={styles.filterRow}>
            <div className={styles.categoryPills} role="tablist" aria-label="Filter by category">
              {GLOSSARY_CATEGORIES.map((cat) => {
                const isActive = selectedCategory === cat.id;
                const count =
                  cat.id === 'all'
                    ? GLOSSARY_TERMS.length
                    : GLOSSARY_TERMS.filter((t) => TERM_CATEGORY_MAP[t] === cat.id).length;

                return (
                  <button
                    key={cat.id}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    className={`${styles.categoryBtn} ${isActive ? styles.categoryBtnActive : ''}`}
                    onClick={() => setSelectedCategory(cat.id)}
                  >
                    <span>{cat.label}</span>
                    <span className="num" style={{ opacity: 0.75, marginLeft: '4px' }}>
                      ({count})
                    </span>
                  </button>
                );
              })}
            </div>

            <span className="num" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
              Showing {filteredTerms.length} of {GLOSSARY_TERMS.length} terms
            </span>
          </div>
        </div>

        {/* Terms list */}
        {filteredTerms.length === 0 ? (
          <div className={styles.emptyGlossary}>
            <h3>No matching glossary terms</h3>
            <p>Try searching for a different keyword or resetting the category filter.</p>
            <button
              type="button"
              className={styles.categoryBtn}
              onClick={() => {
                setSearchQuery('');
                setSelectedCategory('all');
              }}
            >
              Reset filters
            </button>
          </div>
        ) : (
          <dl className={styles.termsGrid}>
            {filteredTerms.map((id) => {
              const e = glossary(id);
              if (!e) return null;
              const catId = TERM_CATEGORY_MAP[id] ?? 'causal';
              const catLabel =
                GLOSSARY_CATEGORIES.find((c) => c.id === catId)?.label ?? 'Definition';
              const isCopied = copiedId === id;

              return (
                <div key={id} id={id} className={styles.termCard}>
                  <div className={styles.termHeader}>
                    <div className={styles.termTitleRow}>
                      <dt className={styles.termName}>
                        <a href={`#${id}`}>{e.label}</a>
                      </dt>
                      <span className="num" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                        #{id}
                      </span>
                    </div>

                    <div className={styles.termActions}>
                      <Badge tone="neutral" variant="outline" size="sm">
                        {catLabel}
                      </Badge>
                      <button
                        type="button"
                        className={styles.copyAnchorBtn}
                        onClick={() => copyAnchor(id)}
                        title="Copy direct link to term"
                        aria-label={`Copy link to ${e.label}`}
                      >
                        {isCopied ? (
                          <Check size={13} style={{ color: 'var(--accent)' }} />
                        ) : (
                          <Link2 size={13} />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Plain Language Definition */}
                  {(viewMode === 'both' || viewMode === 'plain') && (
                    <div className={styles.defBlock}>
                      <span className={styles.defLabel}>
                        <BookOpen size={12} aria-hidden="true" />
                        {C.glossary.plain}
                      </span>
                      <dd className={styles.defTextPlain}>{e.plain}</dd>
                    </div>
                  )}

                  {/* Technical Definition */}
                  {(viewMode === 'both' || viewMode === 'technical') && (
                    <div className={styles.defBlock}>
                      <span className={styles.defLabel}>
                        <Binary size={12} aria-hidden="true" />
                        {C.glossary.technical}
                      </span>
                      <dd className={styles.defTextTechnical}>{e.technical}</dd>
                    </div>
                  )}
                </div>
              );
            })}
          </dl>
        )}
      </section>

      {/* 9. CLOSING CTA BANNER */}
      <aside className={styles.closingCta} aria-label="Explore GroundTruth">
        <div className={styles.ctaTextGroup}>
          <h2 className={styles.ctaTitle}>Inspect Verified Project Evidence</h2>
          <p className={styles.ctaBody}>
            See the method applied across historical carbon project cases, inspect sensitivity
            curves, and review full evidence bundles.
          </p>
        </div>
        <div className={styles.ctaActions}>
          <LinkButton href="/app" variant="primary" icon={<ArrowRight size={16} />}>
            Open Workspace
          </LinkButton>
          <LinkButton href="/status" variant="secondary" icon={<ExternalLink size={16} />}>
            Engine Status & Versions
          </LinkButton>
        </div>
      </aside>
    </div>
  );
}
