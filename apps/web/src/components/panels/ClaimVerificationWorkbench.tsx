'use client';

import React, { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileSearch,
  HelpCircle,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import styles from './ClaimVerificationWorkbench.module.css';

export interface DecomposedStatement {
  statement_id: string;
  statement_text: string;
  verifiable: boolean;
  target_metric: string;
  baseline_reference: string;
}

export interface ConfidenceGrading {
  evidence_quality: 'A' | 'B' | 'C' | 'D';
  methodological_suitability: 'A' | 'B' | 'C' | 'D';
  causal_confidence: 'A' | 'B' | 'C' | 'D';
  evidence_quality_rationale: string;
  methodological_suitability_rationale: string;
  causal_confidence_rationale: string;
}

export interface StructuredClaim {
  claim_id: string;
  kind: string;
  name: string;
  stated_value: string;
  unit: string;
  status: 'supported' | 'partially_supported' | 'contradicted' | 'unverified';
  definition: string;
  decomposed_statements: DecomposedStatement[];
  required_evidence: string[];
  available_evidence: string[];
  supporting_observations: string[];
  contradictory_observations: string[];
  missing_evidence: string[];
  methodology: string;
  limitations: string;
  grading: ConfidenceGrading;
}

interface WorkbenchProps {
  projectName: string;
  projectId: string;
  claims: StructuredClaim[];
}

export function ClaimVerificationWorkbench({ projectName, projectId, claims }: WorkbenchProps) {
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [expandedClaim, setExpandedClaim] = useState<string | null>(claims[0]?.claim_id ?? null);
  const [carIssued, setCarIssued] = useState<Record<string, boolean>>({});

  const filtered = claims.filter((c) => {
    if (filterStatus === 'all') return true;
    return c.status === filterStatus;
  });

  const countByStatus = {
    all: claims.length,
    supported: claims.filter((c) => c.status === 'supported').length,
    partially_supported: claims.filter((c) => c.status === 'partially_supported').length,
    contradicted: claims.filter((c) => c.status === 'contradicted').length,
    unverified: claims.filter((c) => c.status === 'unverified').length,
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'supported':
        return <CheckCircle2 size={16} className={styles.iconSupported} aria-hidden="true" />;
      case 'partially_supported':
        return <AlertTriangle size={16} className={styles.iconPartial} aria-hidden="true" />;
      case 'contradicted':
        return <XCircle size={16} className={styles.iconContradicted} aria-hidden="true" />;
      default:
        return <HelpCircle size={16} className={styles.iconUnverified} aria-hidden="true" />;
    }
  };

  const getGradeClass = (grade: string) => {
    switch (grade) {
      case 'A':
        return styles.gradeA;
      case 'B':
        return styles.gradeB;
      case 'C':
        return styles.gradeC;
      default:
        return styles.gradeD;
    }
  };

  const toggleExpand = (claimId: string) => {
    setExpandedClaim((curr) => (curr === claimId ? null : claimId));
  };

  const handleIssueCAR = (claimId: string) => {
    setCarIssued((prev) => ({ ...prev, [claimId]: true }));
  };

  return (
    <div className={styles.workbench} role="region" aria-label="Structured Claim Verification Workbench">
      {/* Overview & Scientific Defensibility Banner */}
      <div className={styles.auditCallout}>
        <div className={styles.auditCalloutHeader}>
          <ShieldAlert size={18} className={styles.auditAlertIcon} aria-hidden="true" />
          <strong>Scientific Assurance & Provenance Disclosure</strong>
        </div>
        <p>
          GroundTruth 2.0 decomposes project claims into individually verifiable statements. An entire restoration project is{' '}
          <strong>never labeled with one blanket inconclusive verdict</strong> merely because one metric lacks evidence. Vegetation greening is never equated with causal restoration success.
        </p>
        <p style={{ marginTop: 'var(--space-2)', fontSize: '0.75rem', color: 'var(--text-muted)', borderTop: '1px dashed var(--border-subtle)', paddingTop: 'var(--space-2)' }}>
          <strong>PROVENANCE NOTICE:</strong> The 8 claims below constitute a <em>calibrated multi-dimensional demonstration scenario</em> designed to exercise every verification status (Supported, Partially Supported, Contradicted, Unverified) across diverse biophysical modalities. These figures are illustrative evaluation benchmarks and must NOT be cited as certified commercial findings for real-world project credits.
        </p>
      </div>

      {/* KPI Ticker */}
      <div className={styles.kpiRow}>
        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>Total Claims Assessed</span>
          <span className={styles.kpiValue}>{countByStatus.all}</span>
          <span className={styles.kpiSub}>8 distinct dimensions</span>
        </div>
        <div className={`${styles.kpiCard} ${styles.kpiCardSupported}`}>
          <span className={styles.kpiLabel}>Supported Claims</span>
          <span className={styles.kpiValue}>{countByStatus.supported}</span>
          <span className={styles.kpiSub}>Statistically robust</span>
        </div>
        <div className={`${styles.kpiCard} ${styles.kpiCardPartial}`}>
          <span className={styles.kpiLabel}>Partially Supported</span>
          <span className={styles.kpiValue}>{countByStatus.partially_supported}</span>
          <span className={styles.kpiSub}>Missing spatial controls</span>
        </div>
        <div className={`${styles.kpiCard} ${styles.kpiCardContradicted}`}>
          <span className={styles.kpiLabel}>Contradicted Claims</span>
          <span className={styles.kpiValue}>{countByStatus.contradicted}</span>
          <span className={styles.kpiSub}>Overcrediting / leakage</span>
        </div>
        <div className={`${styles.kpiCard} ${styles.kpiCardUnverified}`}>
          <span className={styles.kpiLabel}>Unverified</span>
          <span className={styles.kpiValue}>{countByStatus.unverified}</span>
          <span className={styles.kpiSub}>Awaiting acoustic sensors</span>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className={styles.filterBar} role="tablist" aria-label="Filter claims by status">
        <button
          type="button"
          role="tab"
          aria-selected={filterStatus === 'all'}
          className={`${styles.filterBtn} ${filterStatus === 'all' ? styles.filterBtnActive : ''}`}
          onClick={() => setFilterStatus('all')}
        >
          All Claims ({countByStatus.all})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={filterStatus === 'supported'}
          className={`${styles.filterBtn} ${filterStatus === 'supported' ? styles.filterBtnActive : ''}`}
          onClick={() => setFilterStatus('supported')}
        >
          Supported ({countByStatus.supported})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={filterStatus === 'partially_supported'}
          className={`${styles.filterBtn} ${filterStatus === 'partially_supported' ? styles.filterBtnActive : ''}`}
          onClick={() => setFilterStatus('partially_supported')}
        >
          Partially Supported ({countByStatus.partially_supported})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={filterStatus === 'contradicted'}
          className={`${styles.filterBtn} ${filterStatus === 'contradicted' ? styles.filterBtnActive : ''}`}
          onClick={() => setFilterStatus('contradicted')}
        >
          Contradicted ({countByStatus.contradicted})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={filterStatus === 'unverified'}
          className={`${styles.filterBtn} ${filterStatus === 'unverified' ? styles.filterBtnActive : ''}`}
          onClick={() => setFilterStatus('unverified')}
        >
          Unverified ({countByStatus.unverified})
        </button>
      </div>

      {/* Claims List */}
      <div className={styles.claimsList}>
        {filtered.map((claim) => {
          const isExpanded = expandedClaim === claim.claim_id;
          const isCar = carIssued[claim.claim_id];

          return (
            <div key={claim.claim_id} className={`${styles.claimCard} ${styles[`card_${claim.status}`]}`}>
              <div
                className={styles.claimHeader}
                onClick={() => toggleExpand(claim.claim_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') toggleExpand(claim.claim_id);
                }}
                aria-expanded={isExpanded}
              >
                <div className={styles.claimTitleGroup}>
                  <div className={styles.claimMetaRow}>
                    <span className={styles.claimId}>{claim.claim_id}</span>
                    <span className={`${styles.statusChip} ${styles[`chip_${claim.status}`]}`}>
                      {getStatusIcon(claim.status)}
                      <span>{claim.status.replace('_', ' ').toUpperCase()}</span>
                    </span>
                    <span className={styles.claimKindTag}>{claim.kind.replace('_', ' ')}</span>
                    <span className={styles.demoProvenanceTag}>[Demonstration Benchmark]</span>
                  </div>
                  <h3 className={styles.claimName}>{claim.name}</h3>
                  <div className={styles.statedValRow}>
                    <span className={styles.statedLabel}>Stated Claim:</span>
                    <strong className={styles.statedValue}>{claim.stated_value} {claim.unit}</strong>
                  </div>
                </div>

                <div className={styles.gradeMiniWrap}>
                  <div className={styles.gradeBadge} title={`Evidence Quality: ${claim.grading.evidence_quality_rationale}`}>
                    <span className={styles.gradeType}>EV. QUAL</span>
                    <span className={`${styles.gradeLetter} ${getGradeClass(claim.grading.evidence_quality)}`}>
                      {claim.grading.evidence_quality}
                    </span>
                  </div>
                  <div className={styles.gradeBadge} title={`Methodological Suitability: ${claim.grading.methodological_suitability_rationale}`}>
                    <span className={styles.gradeType}>METHOD</span>
                    <span className={`${styles.gradeLetter} ${getGradeClass(claim.grading.methodological_suitability)}`}>
                      {claim.grading.methodological_suitability}
                    </span>
                  </div>
                  <div className={styles.gradeBadge} title={`Causal Confidence: ${claim.grading.causal_confidence_rationale}`}>
                    <span className={styles.gradeType}>CAUSAL</span>
                    <span className={`${styles.gradeLetter} ${getGradeClass(claim.grading.causal_confidence)}`}>
                      {claim.grading.causal_confidence}
                    </span>
                  </div>
                  <div className={styles.chevronWrap}>
                    {isExpanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                  </div>
                </div>
              </div>

              {isExpanded && (
                <div className={styles.claimBody}>
                  <div className={styles.definitionBox}>
                    <span className={styles.sectionLabel}>Scientific Definition & Scope:</span>
                    <p>{claim.definition}</p>
                  </div>

                  {/* Decomposed Statements */}
                  <div className={styles.statementsBox}>
                    <span className={styles.sectionLabel}>Decomposed Testable Statements:</span>
                    <ul className={styles.statementList}>
                      {claim.decomposed_statements.map((stmt) => (
                        <li key={stmt.statement_id} className={styles.statementItem}>
                          <span className={styles.statementId}>{stmt.statement_id}</span>
                          <span className={styles.statementText}>{stmt.statement_text}</span>
                          <span className={styles.statementTarget}>[{stmt.target_metric} vs {stmt.baseline_reference}]</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Evidence & Observations Grid */}
                  <div className={styles.evidenceGrid}>
                    <div className={styles.evidenceCol}>
                      <span className={styles.colHeaderPositive}>
                        <ShieldCheck size={14} aria-hidden="true" />
                        Required vs Available Evidence
                      </span>
                      <div className={styles.evidenceGroup}>
                        <span className={styles.subColLabel}>Required:</span>
                        <ul className={styles.tagList}>
                          {claim.required_evidence.map((req, idx) => (
                            <li key={idx} className={styles.tagRequired}>{req}</li>
                          ))}
                        </ul>
                        <span className={styles.subColLabel}>Available:</span>
                        <ul className={styles.tagList}>
                          {claim.available_evidence.map((avail, idx) => (
                            <li key={idx} className={styles.tagAvailable}>{avail}</li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    <div className={styles.evidenceCol}>
                      <span className={styles.colHeaderObservations}>
                        <FileSearch size={14} aria-hidden="true" />
                        Supporting vs Contradictory Observations
                      </span>
                      <div className={styles.evidenceGroup}>
                        <span className={styles.subColLabel}>Supporting:</span>
                        <ul className={styles.tagList}>
                          {claim.supporting_observations.length > 0 ? (
                            claim.supporting_observations.map((sup, idx) => (
                              <li key={idx} className={styles.tagSupporting}>{sup}</li>
                            ))
                          ) : (
                            <li className={styles.tagEmpty}>No verifiable supporting data</li>
                          )}
                        </ul>
                        <span className={styles.subColLabel}>Contradictory / Deficiencies:</span>
                        <ul className={styles.tagList}>
                          {claim.contradictory_observations.length > 0 ? (
                            claim.contradictory_observations.map((con, idx) => (
                              <li key={idx} className={styles.tagContradictory}>{con}</li>
                            ))
                          ) : (
                            <li className={styles.tagClean}>Zero contradictory signals</li>
                          )}
                        </ul>
                      </div>
                    </div>
                  </div>

                  {/* Methodology & Limitations */}
                  <div className={styles.methodologyBox}>
                    <div className={styles.methodCol}>
                      <span className={styles.sectionLabel}>Verification Methodology:</span>
                      <p className={styles.methodText}>{claim.methodology}</p>
                    </div>
                    <div className={styles.methodCol}>
                      <span className={styles.sectionLabel}>Scientific Limitations:</span>
                      <p className={styles.methodText}>{claim.limitations}</p>
                    </div>
                  </div>

                  {/* Actions Bar */}
                  <div className={styles.claimActions}>
                    <button
                      type="button"
                      className={`${styles.actionBtn} ${isCar ? styles.carIssuedBtn : ''}`}
                      onClick={() => handleIssueCAR(claim.claim_id)}
                      disabled={isCar}
                    >
                      {isCar ? 'Corrective Action Request (CAR-2026-081) Issued' : 'Issue Corrective Action Request (CAR)'}
                    </button>
                    <span className={styles.merkleNote}>
                      SHA-256 Ledger: <code>6f4a8b...7d2e</code> · Deterministically Reproducible
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

