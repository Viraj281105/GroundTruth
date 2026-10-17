'use client';

import React, { useEffect, useState, useRef } from 'react';
import { Evidence } from '../../lib/types';
import { formatEvidenceValue, formatConfidenceInterval } from '../../lib/formatters';
import { Badge } from './Badge';
import { Button } from './Button';
import {
  X,
  ExternalLink,
  GitBranch,
  Clock,
  Code,
  Database,
  Info,
  Copy,
  Check,
  Sigma,
} from 'lucide-react';
import { describeMethod } from '../../lib/method-descriptions';
import styles from './ProvenanceDrawer.module.css';

function formatQualifier(value: unknown): string {
  if (typeof value === 'string') return value;
  // Six significant figures hides binary noise (0.050000000000000044) without
  // rounding away anything a reader could act on.
  if (typeof value === 'number' && Number.isFinite(value) && !Number.isInteger(value)) {
    return String(Number(value.toPrecision(6)));
  }
  return JSON.stringify(value);
}

export interface ProvenanceDrawerProps {
  evidence: Evidence | null;
  isOpen: boolean;
  onClose: () => void;
}

export const ProvenanceDrawer: React.FC<ProvenanceDrawerProps> = ({
  evidence,
  isOpen,
  onClose,
}) => {
  const [copied, setCopied] = useState(false);
  const drawerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      window.addEventListener('keydown', handleKeyDown);
      // Focus drawer for keyboard navigation
      setTimeout(() => drawerRef.current?.focus(), 50);
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen || !evidence) return null;

  const { provenance } = evidence;
  const description = describeMethod(provenance.method);
  const hasParameters = Object.keys(provenance.parameters ?? {}).length > 0;
  const qualifierEntries = Object.entries(evidence.qualifiers ?? {});

  const handleCopyParameters = () => {
    if (provenance.parameters) {
      navigator.clipboard.writeText(JSON.stringify(provenance.parameters, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div
      className={styles.overlay}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="provenance-title"
      aria-describedby="provenance-desc"
    >
      <div
        ref={drawerRef}
        className={styles.drawer}
        onClick={(e) => e.stopPropagation()}
        tabIndex={-1}
      >
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <div className={styles.stageBadgeRow}>
              <Badge tone="info" size="sm" variant="subtle">
                STAGE: {provenance.stage.toUpperCase()}
              </Badge>
              <Badge tone="neutral" size="sm" variant="outline" className={styles.wrapBadge}>
                ID: {evidence.id}
              </Badge>
            </div>
            <h2 id="provenance-title" className={styles.title}>
              {evidence.label}
            </h2>
          </div>
          <button
            className={styles.closeButton}
            onClick={onClose}
            aria-label="Close provenance drawer"
          >
            <X size={20} />
          </button>
        </div>

        {/* Value Hero Display */}
        <div id="provenance-desc" className={styles.valueHero}>
          <span className={styles.valueHeroLabel}>VALUE</span>
          <div className={styles.valueHeroNumber}>
            {formatEvidenceValue(evidence.value, evidence.unit)}
          </div>
          {evidence.confidence && (
            <div className={styles.confidenceBadge}>
              <Badge tone="neutral" size="sm" className={styles.wrapBadge}>
                {formatConfidenceInterval(evidence.confidence, evidence.unit)}
              </Badge>
            </div>
          )}
        </div>

        {/* Provenance Metadata Sections */}
        <div className={styles.body}>
          {/* Method & Derivation */}
          <div className={styles.section}>
            <div className={styles.sectionTitle}>
              <Code size={16} />
              <span>Computational Method</span>
            </div>
            <div className={styles.metaCard}>
              <div className={styles.metaRow}>
                <span className={styles.metaKey}>Method:</span>
                <span className={styles.metaValMono}>{provenance.method}</span>
              </div>
              <div className={styles.metaRow}>
                <span className={styles.metaKey}>Pipeline Stage:</span>
                <span className={styles.metaVal}>{provenance.stage}</span>
              </div>
              {provenance.code_version && (
                <div className={styles.metaRow}>
                  <span className={styles.metaKey}>Code Version:</span>
                  <span className={styles.metaValMono}>{provenance.code_version}</span>
                </div>
              )}
            </div>
          </div>

          {/* Data Source & Origin */}
          <div className={styles.section}>
            <div className={styles.sectionTitle}>
              <Database size={16} />
              <span>Data Source & Origin</span>
            </div>
            <div className={styles.metaCard}>
              <div className={styles.metaRow}>
                <span className={styles.metaKey}>Source Name:</span>
                <span className={styles.metaVal}>{provenance.source}</span>
              </div>
              {provenance.source_uri && (
                <div className={styles.metaRow}>
                  <span className={styles.metaKey}>Source URI:</span>
                  <a
                    href={provenance.source_uri}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.sourceLink}
                  >
                    <span>{provenance.source_uri}</span>
                    <ExternalLink size={12} />
                  </a>
                </div>
              )}
              {provenance.retrieved_at && (
                <div className={styles.metaRow}>
                  <span className={styles.metaKey}>Retrieved At:</span>
                  <span className={styles.metaVal}>
                    <Clock size={12} className={styles.inlineIcon} />
                    {new Date(provenance.retrieved_at).toLocaleString()}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* What the method does, read from provenance.method. An unknown
              method gets no description: the method string above and the
              parameters below are all that is shown. */}
          <div className={styles.section}>
            <div className={styles.sectionTitle}>
              <Sigma size={16} />
              <span>Method</span>
            </div>
            {description ? (
              <div className={styles.methodCard}>
                <div className={styles.methodTitle}>{description.title}</div>
                {description.summary.map((paragraph, i) => (
                  <p key={i} className={styles.methodText}>
                    {paragraph}
                  </p>
                ))}
                {description.formula && (
                  <div className={styles.mathCard} aria-label="Formula">
                    {description.formula.map((line, i) => (
                      <div key={i} className={styles.mathEquation}>
                        {line}
                      </div>
                    ))}
                  </div>
                )}
                {description.caveat && (
                  <p className={styles.methodCaveat}>{description.caveat}</p>
                )}
              </div>
            ) : (
              <p className={styles.methodUnknown}>
                No description is available for <code>{provenance.method}</code>.{' '}
                {hasParameters
                  ? 'Its parameters below are the only record of how this value was produced.'
                  : 'No parameters were recorded for it.'}
              </p>
            )}
          </div>

          {/* Execution Parameters JSON */}
          {hasParameters && (
            <div className={styles.section}>
              <div className={styles.sectionTitleRow}>
                <div className={styles.sectionTitle}>
                  <GitBranch size={16} />
                  <span>Execution Parameters</span>
                </div>
                <button
                  type="button"
                  className={styles.copyBtn}
                  onClick={handleCopyParameters}
                  aria-label="Copy parameters JSON"
                >
                  {copied ? <Check size={12} /> : <Copy size={12} />}
                  <span>{copied ? 'Copied' : 'Copy JSON'}</span>
                </button>
              </div>
              <pre className={styles.codeBlock}>
                {JSON.stringify(provenance.parameters, null, 2)}
              </pre>
            </div>
          )}

          {/* Upstream Evidence Inputs Graph */}
          {provenance.inputs && provenance.inputs.length > 0 && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <GitBranch size={16} />
                <span>Upstream Evidence Inputs</span>
              </div>
              <div className={styles.inputsList}>
                {provenance.inputs.map((inp, i) => (
                  <span key={i} className={styles.inputItem}>
                    <code>{inp}</code>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Scientific Notes */}
          {provenance.notes && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <Info size={16} />
                <span>Scientific Notes</span>
              </div>
              <p className={styles.notesText}>{provenance.notes}</p>
            </div>
          )}

          {/* Qualifiers: conditions the engine attached to this value */}
          {qualifierEntries.length > 0 && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <Info size={16} />
                <span>Qualifiers</span>
              </div>
              <div className={styles.metaCard}>
                {qualifierEntries.map(([key, val]) => (
                  <div key={key} className={styles.metaRow}>
                    <span className={styles.metaKey}>{key}:</span>
                    <span className={styles.metaValMono}>{formatQualifier(val)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          <Button variant="secondary" size="md" onClick={onClose}>
            Close Provenance
          </Button>
        </div>
      </div>
    </div>
  );
};
