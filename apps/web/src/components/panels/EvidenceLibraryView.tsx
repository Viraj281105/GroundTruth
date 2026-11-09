'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { Copy, ExternalLink, FileCode, Search, ShieldCheck } from 'lucide-react';
import { Chip, EmptyState, UnavailablePanel } from '../ds';
import {
  FILTERS,
  classificationChips,
  completenessOf,
  coverageText,
  filterSources,
  lifecycleCounts,
  qualityText,
  retrievalText,
  shortHash,
  type Filter,
  type ProjectDocsRow,
  type Registry,
  type RegistrySource,
} from './evidenceLibrary.model';
import styles from './EvidenceLibraryView.module.css';

interface Props {
  /** The registry as the API returned it, or null when it could not be loaded. No defaults exist. */
  registry: Registry | null;
  /** Why the registry is missing (shown instead of any data). */
  error?: string | null;
  orgSlug: string;
  /** The organization's projects and their uploaded-document counts; null when the project list could not be loaded. */
  projects: ProjectDocsRow[] | null;
}

const dash = (v: string | null | undefined, fallback = 'Not recorded') => (v && v.trim() ? v : fallback);

export function EvidenceLibraryView({ registry, error, orgSlug, projects }: Props) {
  const [filterState, setFilterState] = useState<Filter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSource, setSelectedSource] = useState<RegistrySource | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  const header = (
    <div className={styles.header}>
      <div className={styles.titleArea}>
        <span className={styles.kicker}>Reference datasets</span>
        <h1 className={styles.title}>Evidence Library & Dataset Registry</h1>
        <p className={styles.desc}>
          The public catalogue of data sources GroundTruth knows about, and an honest account of which ones it can actually use today. This is
          reference information, not your organization&apos;s own evidence: your uploaded documents are listed per project below.
        </p>
      </div>
    </div>
  );

  if (!registry) {
    return (
      <div className={styles.container}>
        {header}
        <UnavailablePanel
          title="Dataset registry"
          reason={error ?? 'The dataset registry could not be loaded.'}
          evidenceNeeded="A reachable GroundTruth API. No substitute list is shown, because an invented dataset list would be misleading."
        />
        <ProjectDocs orgSlug={orgSlug} projects={projects} />
      </div>
    );
  }

  const sources = Array.isArray(registry.sources) ? registry.sources : [];
  const counts = lifecycleCounts(sources);
  const filtered = filterSources(sources, filterState, searchQuery);

  const copyHash = (hash: string) => {
    navigator.clipboard?.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2500);
  };

  return (
    <div className={styles.container}>
      {header}

      <div className={styles.failClosedNotice}>
        <div className={styles.noticeIconWrap}>
          <ShieldCheck size={20} className={styles.noticeIcon} />
        </div>
        <div className={styles.noticeBody}>
          <strong>Registry summary:</strong>
          <span>
            {registry.total_registered} sources catalogued · {registry.operational_count} with an operational ingestion path ·{' '}
            {registry.usable_for_production_count} usable for production analysis · {registry.blocked_count} blocked · {registry.synthetic_count}{' '}
            simulated. A source that is only catalogued, staged by hand or not validated is never used for a verified result.
          </span>
        </div>
      </div>

      <div className={styles.controlBar}>
        <div className={styles.filterTabs} role="group" aria-label="Filter by lifecycle">
          {FILTERS.map((f) => (
            <button key={f} type="button" className={`${styles.filterTab} ${filterState === f ? styles.tabActive : ''}`} onClick={() => setFilterState(f)}>
              {f === 'all' ? 'All sources' : f.charAt(0).toUpperCase() + f.slice(1)} ({counts[f]})
            </button>
          ))}
        </div>
        <div className={styles.searchBox}>
          <Search size={16} className={styles.searchIcon} />
          <input
            type="text"
            aria-label="Search datasets"
            placeholder="Search datasets, providers, modalities..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={styles.searchInput}
          />
        </div>
      </div>

      {filtered.length === 0 && <EmptyState title="No datasets match" body="Try another filter or search term." />}

      <div className={styles.grid}>
        {filtered.map((s) => {
          const completeness = completenessOf(s);
          const hash = s.content_hash;
          const chips = classificationChips(s);
          return (
            <div key={s.source_id} className={`${styles.card} ${s.lifecycle === 'quarantined' ? styles.cardQuarantined : ''}`} data-source-id={s.source_id}>
              <div className={styles.cardHeader}>
                <span className={styles.sourceId}>{s.source_id}</span>
                <h3 className={styles.cardTitle}>{s.title}</h3>
                <span className={styles.providerName}>
                  {s.provider} · v{s.version}
                </span>
                <div className={styles.chipRow}>
                  {chips.map((c) => (
                    <Chip key={c.key} tone={c.tone}>
                      {c.label}
                    </Chip>
                  ))}
                </div>
              </div>

              <div className={styles.cardBody}>
                <Row label="Data type" value={dash(s.modality, 'Not stated').toUpperCase()} />
                <Row label="Resolution" value={`${dash(s.spatial_resolution, 'n/a')} · ${dash(s.temporal_resolution, 'n/a')}`} />
                <Row label="Spatial coverage" value={dash(s.spatial_coverage, 'Not stated')} />
                <Row label="Time coverage" value={coverageText(s)} />
                <Row label="Retrieved" value={retrievalText(s)} />
                <Row label="Acquisition date" value={dash(s.acquisition_date)} />
                <Row label="License" value={dash(s.license, 'Not stated')} />
                <Row label="Quality" value={qualityText(s)} />
                <div className={styles.metaRow}>
                  <span className={styles.metaLabel}>Completeness:</span>
                  {completeness === null ? (
                    <span className={styles.metaVal}>Not measured</span>
                  ) : (
                    <div className={styles.barWrap}>
                      <div className={styles.barFill} style={{ width: `${completeness}%` }} />
                      <span className={styles.barText}>{completeness}%</span>
                    </div>
                  )}
                </div>
                <Row label="Validation" value={`${dash(s.validation_status, 'unknown')} · evidence: ${dash(s.validation_evidence, 'none')}`} />

                {s.blocked_for_production_analysis && (
                  <p className={styles.note} data-blocked-reason>
                    <strong>Why it is blocked:</strong> {dash(s.blocked_reason, 'No reason given by the API.')}
                  </p>
                )}
                {s.quarantine_reason && (
                  <p className={styles.note}>
                    <strong>Quarantine:</strong> {s.quarantine_reason}
                  </p>
                )}

                <div className={styles.hashRow}>
                  <span className={styles.hashLabel}>SHA-256:</span>
                  {hash ? (
                    <>
                      <code className={styles.hashCode} title={hash}>
                        {shortHash(hash)}
                      </code>
                      <button type="button" className={styles.copyBtn} onClick={() => copyHash(hash)} title="Copy full SHA-256 hash">
                        <Copy size={12} />
                        {copiedHash === hash ? 'Copied' : 'Copy'}
                      </button>
                    </>
                  ) : (
                    <span className={styles.hashCode}>No local copy, so no checksum</span>
                  )}
                </div>
              </div>

              <div className={styles.cardFooter}>
                {s.source_url ? (
                  <a href={s.source_url} target="_blank" rel="noopener noreferrer" className={styles.sourceLink}>
                    <span>Original provider</span>
                    <ExternalLink size={12} />
                  </a>
                ) : (
                  <span className={styles.sourceLink}>No source link</span>
                )}
                <button type="button" className={styles.provenanceBtn} onClick={() => setSelectedSource(s)}>
                  <FileCode size={14} />
                  <span>Full record</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <ProjectDocs orgSlug={orgSlug} projects={projects} />

      {selectedSource && (
        <div className={styles.modalOverlay} onClick={() => setSelectedSource(null)}>
          <div className={styles.modalContent} role="dialog" aria-label="Dataset record" onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <div>
                <span className={styles.kicker}>Registry record, exactly as the API returns it</span>
                <h2 className={styles.modalTitle}>{selectedSource.title}</h2>
              </div>
              <button type="button" className={styles.closeBtn} onClick={() => setSelectedSource(null)} aria-label="Close">
                ✕
              </button>
            </div>
            <div className={styles.modalBody}>
              <pre className={styles.jsonCode}>{JSON.stringify(selectedSource, null, 2)}</pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metaRow}>
      <span className={styles.metaLabel}>{label}:</span>
      <span className={styles.metaVal}>{value}</span>
    </div>
  );
}

function ProjectDocs({ orgSlug, projects }: { orgSlug: string; projects: ProjectDocsRow[] | null }) {
  return (
    <section className={styles.projectDocs} aria-label="Your project documents">
      <h2 className={styles.sectionTitle}>Your organization&apos;s project documents</h2>
      <p className={styles.desc}>Documents are uploaded and managed on each project&apos;s Evidence tab.</p>
      {projects === null ? (
        <p className={styles.note}>The project list could not be loaded, so document counts are unknown.</p>
      ) : projects.length === 0 ? (
        <EmptyState title="No projects yet" body="Create a project to upload its documents." action={<Link href={`/app/${orgSlug}/projects/new`}>Create a project</Link>} />
      ) : (
        <ul className={styles.projectList}>
          {projects.map((p) => (
            <li key={p.id}>
              <Link href={`/app/${orgSlug}/projects/${p.slug}/evidence`}>{p.name}</Link>
              <span className={styles.metaLabel}>
                {p.documentsCount === null ? 'document count unknown' : `${p.documentsCount} uploaded document${p.documentsCount === 1 ? '' : 's'}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
