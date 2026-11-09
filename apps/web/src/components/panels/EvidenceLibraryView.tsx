'use client';

import React, { useState } from 'react';
import {
  AlertOctagon,
  CheckCircle2,
  Copy,
  Database,
  ExternalLink,
  FileCheck,
  FileCode,
  Filter,
  Layers,
  Lock,
  Search,
  ShieldCheck,
} from 'lucide-react';
import styles from './EvidenceLibraryView.module.css';

export interface EvidenceSourceItem {
  source_id: string;
  name: string;
  provider: string;
  original_url: string;
  dataset_identifier: string;
  version: string;
  license: string;
  permitted_usage: string;
  spatial_coverage: string;
  temporal_coverage: string;
  resolution: string;
  acquisition_date: string;
  retrieval_timestamp: string;
  processing_history: string[];
  data_quality: string;
  completeness_pct: number;
  content_sha256: string;
  lifecycle: 'discovered' | 'accessible' | 'integrated' | 'validated' | 'quarantined';
  modality: string;
}

interface Props {
  sources: EvidenceSourceItem[];
  orgSlug: string;
}

export function EvidenceLibraryView({ sources, orgSlug }: Props) {
  const [filterState, setFilterState] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedSource, setSelectedSource] = useState<EvidenceSourceItem | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  const filtered = sources.filter((s) => {
    if (filterState !== 'all' && s.lifecycle !== filterState) return false;
    if (searchQuery.trim() === '') return true;
    const q = searchQuery.toLowerCase();
    return (
      s.name.toLowerCase().includes(q) ||
      s.provider.toLowerCase().includes(q) ||
      s.source_id.toLowerCase().includes(q) ||
      s.modality.toLowerCase().includes(q)
    );
  });

  const counts = {
    all: sources.length,
    validated: sources.filter((s) => s.lifecycle === 'validated').length,
    integrated: sources.filter((s) => s.lifecycle === 'integrated').length,
    accessible: sources.filter((s) => s.lifecycle === 'accessible').length,
    discovered: sources.filter((s) => s.lifecycle === 'discovered').length,
    quarantined: sources.filter((s) => s.lifecycle === 'quarantined').length,
  };

  const copyHash = (hash: string) => {
    navigator.clipboard?.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2500);
  };

  const getLifecycleBadge = (lifecycle: string) => {
    switch (lifecycle) {
      case 'validated':
        return <span className={`${styles.lifecycleChip} ${styles.chipValidated}`}><CheckCircle2 size={12} /> Validated (Operational)</span>;
      case 'integrated':
        return <span className={`${styles.lifecycleChip} ${styles.chipIntegrated}`}><FileCheck size={12} /> Integrated (Operational)</span>;
      case 'accessible':
        return <span className={`${styles.lifecycleChip} ${styles.chipAccessible}`}><Lock size={12} /> Accessible (Pre-production)</span>;
      case 'discovered':
        return <span className={`${styles.lifecycleChip} ${styles.chipDiscovered}`}><Database size={12} /> Discovered (Catalogue only)</span>;
      case 'quarantined':
        return <span className={`${styles.lifecycleChip} ${styles.chipQuarantined}`}><AlertOctagon size={12} /> Quarantined (Blocked)</span>;
      default:
        return null;
    }
  };

  return (
    <div className={styles.container}>
      {/* Page Header */}
      <div className={styles.header}>
        <div className={styles.titleArea}>
          <span className={styles.kicker}>Scientific Data Integrity & Provenance</span>
          <h1 className={styles.title}>Evidence Library & Dataset Registry</h1>
          <p className={styles.desc}>
            Cryptographically tracked environmental observations, remote sensing providers, spatial boundaries, and climate time-series.
            Every dataset maintains an immutable SHA-256 fingerprint, permitted usage terms, and explicit operational lifecycle state.
          </p>
        </div>
      </div>

      {/* Quarantined Gate Warning */}
      <div className={styles.failClosedNotice}>
        <div className={styles.noticeIconWrap}>
          <ShieldCheck size={20} className={styles.noticeIcon} />
        </div>
        <div className={styles.noticeBody}>
          <strong>Fail-Closed Scientific Gateway Active:</strong>
          <span>
            Datasets marked <code>discovered</code> or <code>accessible</code> are catalogued for research but{' '}
            <em>strictly refused</em> by analytical reduction pipelines. Quarantined datasets (e.g., checksum drift or unverified pipelines) are completely isolated to guarantee zero hallucinated metrics.
          </span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className={styles.controlBar}>
        <div className={styles.filterTabs} role="tablist">
          <button
            type="button"
            className={`${styles.filterTab} ${filterState === 'all' ? styles.tabActive : ''}`}
            onClick={() => setFilterState('all')}
          >
            All Sources ({counts.all})
          </button>
          <button
            type="button"
            className={`${styles.filterTab} ${filterState === 'validated' ? styles.tabActive : ''}`}
            onClick={() => setFilterState('validated')}
          >
            Validated ({counts.validated})
          </button>
          <button
            type="button"
            className={`${styles.filterTab} ${filterState === 'integrated' ? styles.tabActive : ''}`}
            onClick={() => setFilterState('integrated')}
          >
            Integrated ({counts.integrated})
          </button>
          <button
            type="button"
            className={`${styles.filterTab} ${filterState === 'accessible' ? styles.tabActive : ''}`}
            onClick={() => setFilterState('accessible')}
          >
            Accessible ({counts.accessible})
          </button>
          <button
            type="button"
            className={`${styles.filterTab} ${filterState === 'discovered' ? styles.tabActive : ''}`}
            onClick={() => setFilterState('discovered')}
          >
            Discovered ({counts.discovered})
          </button>
          <button
            type="button"
            className={`${styles.filterTab} ${filterState === 'quarantined' ? styles.tabActive : ''}`}
            onClick={() => setFilterState('quarantined')}
          >
            Quarantined ({counts.quarantined})
          </button>
        </div>

        <div className={styles.searchBox}>
          <Search size={16} className={styles.searchIcon} />
          <input
            type="text"
            placeholder="Search datasets, providers, modalities..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={styles.searchInput}
          />
        </div>
      </div>

      {/* Sources Grid */}
      <div className={styles.grid}>
        {filtered.map((s) => (
          <div key={s.source_id} className={`${styles.card} ${s.lifecycle === 'quarantined' ? styles.cardQuarantined : ''}`}>
            <div className={styles.cardHeader}>
              <div className={styles.headerTopRow}>
                <span className={styles.sourceId}>{s.source_id}</span>
                {getLifecycleBadge(s.lifecycle)}
              </div>
              <h3 className={styles.cardTitle}>{s.name}</h3>
              <span className={styles.providerName}>{s.provider} · v{s.version}</span>
            </div>

            <div className={styles.cardBody}>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>Modality:</span>
                <span className={styles.metaVal}>{s.modality.toUpperCase()}</span>
              </div>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>Resolution:</span>
                <span className={styles.metaVal}>{s.resolution}</span>
              </div>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>Spatial:</span>
                <span className={styles.metaVal}>{s.spatial_coverage}</span>
              </div>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>Temporal:</span>
                <span className={styles.metaVal}>{s.temporal_coverage}</span>
              </div>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>License:</span>
                <span className={styles.metaVal}>{s.license}</span>
              </div>
              <div className={styles.metaRow}>
                <span className={styles.metaLabel}>Completeness:</span>
                <div className={styles.barWrap}>
                  <div className={styles.barFill} style={{ width: `${s.completeness_pct}%` }} />
                  <span className={styles.barText}>{s.completeness_pct}%</span>
                </div>
              </div>

              {/* Hash & Provenance */}
              <div className={styles.hashRow}>
                <span className={styles.hashLabel}>SHA-256:</span>
                <code className={styles.hashCode} title={s.content_sha256}>
                  {s.content_sha256.substring(0, 16)}...
                </code>
                <button
                  type="button"
                  className={styles.copyBtn}
                  onClick={() => copyHash(s.content_sha256)}
                  title="Copy full SHA-256 hash"
                >
                  <Copy size={12} />
                  {copiedHash === s.content_sha256 ? 'Copied' : 'Copy'}
                </button>
              </div>
            </div>

            <div className={styles.cardFooter}>
              <a href={s.original_url} target="_blank" rel="noopener noreferrer" className={styles.sourceLink}>
                <span>Original Provider</span>
                <ExternalLink size={12} />
              </a>
              <button
                type="button"
                className={styles.provenanceBtn}
                onClick={() => setSelectedSource(s)}
              >
                <FileCode size={14} />
                <span>JSON-LD Spec</span>
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* JSON-LD Provenance Modal */}
      {selectedSource && (
        <div className={styles.modalOverlay} onClick={() => setSelectedSource(null)}>
          <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <div>
                <span className={styles.kicker}>Cryptographic Evidence Record</span>
                <h2 className={styles.modalTitle}>{selectedSource.name}</h2>
              </div>
              <button type="button" className={styles.closeBtn} onClick={() => setSelectedSource(null)}>
                ✕
              </button>
            </div>
            <div className={styles.modalBody}>
              <pre className={styles.jsonCode}>
                {JSON.stringify(
                  {
                    '@context': 'https://schema.org',
                    '@type': 'Dataset',
                    name: selectedSource.name,
                    identifier: selectedSource.dataset_identifier,
                    provider: {
                      '@type': 'Organization',
                      name: selectedSource.provider,
                      url: selectedSource.original_url,
                    },
                    version: selectedSource.version,
                    license: selectedSource.license,
                    permittedUsage: selectedSource.permitted_usage,
                    spatialCoverage: selectedSource.spatial_coverage,
                    temporalCoverage: selectedSource.temporal_coverage,
                    resolution: selectedSource.resolution,
                    retrievalTimestamp: selectedSource.retrieval_timestamp,
                    sha256Digest: selectedSource.content_sha256,
                    lifecycleState: selectedSource.lifecycle,
                    processingSteps: selectedSource.processing_history,
                  },
                  null,
                  2
                )}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

