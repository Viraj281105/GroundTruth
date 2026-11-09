import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { EvidenceLibraryView } from '../src/components/panels/EvidenceLibraryView';
import { classificationChips, completenessOf, filterSources, lifecycleCounts, type Registry, type RegistrySource } from '../src/components/panels/evidenceLibrary.model';

/** Test-only values; the shipped code contains no source list. */
const source = (over: Partial<RegistrySource> = {}): RegistrySource => ({
  source_id: 'test-source',
  title: 'Test Dataset',
  provider: 'Test Provider',
  source_url: 'https://example.org/data',
  dataset_identifier: 'test-ds',
  version: '1',
  license: 'CC-BY',
  permitted_usage: 'research',
  modality: 'optical',
  spatial_coverage: 'Global',
  temporal_coverage_start: '2015',
  temporal_coverage_end: 'present',
  spatial_resolution: '10 m',
  temporal_resolution: '5 days',
  acquisition_date: null,
  retrieval_timestamp: null,
  processing_history: [],
  data_quality_score: null,
  completeness_percentage: null,
  missingness_summary: '',
  content_hash: null,
  lifecycle: 'discovered',
  is_operational_integration: false,
  sutva_compliant: false,
  quarantine_reason: null,
  notes: '',
  ingestion_mode: 'accessible_unvalidated',
  validation_status: 'unvalidated',
  validation_evidence: 'none',
  blocked_for_production_analysis: true,
  blocked_reason: 'No validated ingestion path.',
  quality_measured: false,
  quality_note: 'Quality has not been measured from retrieved data.',
  retrieval_status: 'not_retrieved',
  retrieval_provenance: null,
  content_hash_scope: null,
  retrieved_temporal_coverage: null,
  local_artifact_paths: [],
  artifacts_present: null,
  ...over,
});

const registry = (sources: RegistrySource[]): Registry => ({
  total_registered: sources.length,
  discovered: 1,
  accessible: 0,
  integrated: 0,
  validated: 0,
  quarantined: 0,
  operational_count: 0,
  usable_for_production_count: 0,
  blocked_count: sources.length,
  synthetic_count: 0,
  ingestion_mode_counts: {},
  average_completeness: null,
  completeness_measured_count: 0,
  sources,
});

const html = (el: React.ReactElement) => renderToStaticMarkup(el);

describe('EvidenceLibraryView', () => {
  it('renders a source whose nullable fields are all null without throwing', () => {
    const m = html(<EvidenceLibraryView registry={registry([source()])} orgSlug="acme" projects={[]} />);
    expect(m).toContain('Test Dataset');
    expect(m).toContain('Not recorded'); // acquisition date
    expect(m).toContain('Not measured'); // completeness and quality
    expect(m).toContain('No local copy, so no checksum');
    expect(m).toContain('No validated ingestion path.');
    expect(m).not.toContain('0000000000');
  });

  it('never calls a source operational unless the API says so', () => {
    const plain = html(<EvidenceLibraryView registry={registry([source({ lifecycle: 'validated', validation_status: 'validated' })])} orgSlug="acme" projects={[]} />);
    expect(plain).not.toContain('Operational integration');
    const operational = html(
      <EvidenceLibraryView
        registry={registry([source({ is_operational_integration: true, ingestion_mode: 'automated_operational', blocked_for_production_analysis: false, blocked_reason: null })])}
        orgSlug="acme"
        projects={[]}
      />,
    );
    expect(operational).toContain('Operational integration');
    expect(operational).toContain('Usable for production analysis');
  });

  it('shows a measured hash and completeness only when present', () => {
    const m = html(<EvidenceLibraryView registry={registry([source({ content_hash: 'a'.repeat(64), completeness_percentage: 87.5 })])} orgSlug="acme" projects={[]} />);
    expect(m).toContain('aaaaaaaaaaaaaaaa');
    expect(m).toContain('87.5%');
  });

  it('shows an honest error and NO dataset list when the registry could not be loaded', () => {
    const m = html(<EvidenceLibraryView registry={null} error="The dataset registry could not be loaded. The GroundTruth API could not be reached." orgSlug="acme" projects={null} />);
    expect(m).toContain('Dataset registry (unavailable)');
    expect(m).toContain('could not be reached');
    expect(m).not.toContain('data-source-id');
    expect(m).not.toMatch(/sentinel|chirps|sha-256/i);
  });

  it('lists the organization projects with document counts and links to the Evidence tab', () => {
    const m = html(
      <EvidenceLibraryView
        registry={registry([source()])}
        orgSlug="acme"
        projects={[
          { id: '1', slug: 'p-one', name: 'Project One', documentsCount: 2 },
          { id: '2', slug: 'p-two', name: 'Project Two', documentsCount: null },
        ]}
      />,
    );
    expect(m).toContain('/app/acme/projects/p-one/evidence');
    expect(m).toContain('2 uploaded documents');
    expect(m).toContain('document count unknown');
  });

  it('says there are no projects for an empty organization', () => {
    expect(html(<EvidenceLibraryView registry={registry([source()])} orgSlug="acme" projects={[]} />)).toContain('No projects yet');
  });
});

describe('evidence library model', () => {
  it('chips: simulated sources are marked sim, blocked sources say blocked', () => {
    const chips = classificationChips(source({ ingestion_mode: 'synthetic_simulated' }));
    expect(chips.find((c) => c.key === 'mode')?.tone).toBe('sim');
    expect(chips.find((c) => c.key === 'production')?.label).toBe('Blocked for production analysis');
  });
  it('completeness is null (not 0) when unmeasured and clamped when measured', () => {
    expect(completenessOf({ completeness_percentage: null })).toBeNull();
    expect(completenessOf({ completeness_percentage: 140 })).toBe(100);
  });
  it('filters and counts are null-safe', () => {
    const list = [source(), source({ source_id: 'b', title: 'Rain', lifecycle: 'quarantined' })];
    expect(lifecycleCounts(list).quarantined).toBe(1);
    expect(filterSources(list, 'all', 'rain').map((s) => s.source_id)).toEqual(['b']);
    expect(filterSources(list, 'quarantined', '').length).toBe(1);
  });
});
