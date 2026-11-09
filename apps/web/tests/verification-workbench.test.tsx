import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
import { ClaimVerificationWorkbench } from '../src/components/panels/ClaimVerificationWorkbench';
import { claimsProblem, humanize, isSimulated, normalizeStatus, showValue, toPortfolio } from '../src/components/panels/claimWorkbenchModel';

const html = (el: React.ReactElement) => renderToStaticMarkup(el);

const EMPTY = {
  project_id: 'p1',
  project_name: 'New project',
  total_claims: 0,
  claims: [],
  overall_portfolio_grade: 'N/A',
  scientific_guardrails: [],
  data_mode: 'observed',
  is_demo: false,
  notice: null,
  has_claims: false,
  missing_information: [
    { id: 'claims_submitted', label: 'Claims to verify', status: 'not_met', detail: 'No claims have been submitted for this project.', action: 'Upload a project document or paste claim text to extract claims.' },
    { id: 'readiness_unavailable', label: 'Evidence readiness', status: 'unavailable', detail: 'could not be computed', action: 'Add a boundary.' },
  ],
  next_steps: ['Add the project boundary.', 'Upload project documents containing the claims you want checked.'],
};

const CLAIM = {
  claim_id: 'C-1',
  claim_type: 'area_restored',
  title: 'Area restored',
  definition: 'Hectares restored',
  claimed_value: 1200,
  claimed_unit: 'ha',
  observed_value: null,
  observed_unit: null,
  required_evidence: ['Boundary'],
  available_evidence: [],
  supporting_observations: [],
  contradictory_observations: ['Observed area smaller'],
  missing_evidence: ['Orthomosaic'],
  verification_methodology: 'Geodesic area',
  confidence_and_limitations: ['10 m pixels'],
  grading: { evidence_quality_grade: 'C', evidence_quality_score: 60.1, methodological_suitability_grade: 'B', methodological_suitability_score: 72, causal_confidence_grade: 'D', causal_confidence_score: 41, overall_score: 55, overall_grade: 'C', scoring_rationale: ['rationale one'] },
  status: 'PARTIALLY_SUPPORTED',
  discrepancy_percentage: null,
  corrective_action_request: null,
  decomposed_statements: [{ statement_id: 'S-1', statement_text: 'Area is 1200 ha', target_metric: 'area', claimed_value: 1200, observed_value: null, status: 'UNVERIFIED', rationale: 'no data' }],
};

const render = (body: unknown) =>
  html(<ClaimVerificationWorkbench projectName="Proj" orgSlug="acme" projectSlug="proj-1" portfolio={toPortfolio(body)} />);

describe('claim workbench model', () => {
  it('normalises statuses and never promotes unknown ones to supported', () => {
    expect(normalizeStatus('SUPPORTED')).toBe('supported');
    expect(normalizeStatus('PARTIALLY_SUPPORTED')).toBe('partially_supported');
    expect(normalizeStatus(undefined)).toBe('unverified');
    expect(normalizeStatus('weird')).toBe('unverified');
  });
  it('is safe on missing, null and wrongly typed fields', () => {
    for (const body of [null, undefined, 'x', 5, [], {}, { claims: 'nope' }, { claims: [null, 1, {}] }]) {
      expect(() => toPortfolio(body)).not.toThrow();
    }
    const p = toPortfolio({ claims: [null, {}] });
    expect(p.claims).toHaveLength(2);
    expect(p.claims[0].title).toBe('Claim 1');
    expect(p.claims[0].claimedValue).toBe('');
    expect(p.claims[0].grading.evidenceQuality).toBe('');
    expect(() => html(<ClaimVerificationWorkbench projectName="" orgSlug="o" projectSlug="p" portfolio={p} />)).not.toThrow();
  });
  it('shows values exactly as sent and never invents one', () => {
    expect(showValue(1200)).toBe('1,200');
    expect(showValue('84.2')).toBe('84.2');
    expect(showValue(null)).toBe('');
    expect(showValue(undefined)).toBe('');
    expect(humanize(undefined)).toBe('');
    expect(humanize('partially_supported')).toBe('Partially supported');
  });
  it('flags demo and synthetic data', () => {
    expect(isSimulated(toPortfolio({ is_demo: true }))).toBe(true);
    expect(isSimulated(toPortfolio({ data_mode: 'synthetic' }))).toBe(true);
    expect(isSimulated(toPortfolio({ data_mode: 'observed' }))).toBe(false);
  });
  it('gives an honest message per failure status', () => {
    expect(claimsProblem(401)).toMatch(/Sign in/);
    expect(claimsProblem(404)).toMatch(/not found|no access/i);
    expect(claimsProblem(0)).toMatch(/could not be reached/);
    expect(claimsProblem(500)).toMatch(/HTTP 500/);
  });
});

describe('ClaimVerificationWorkbench', () => {
  it('shows a helpful empty state for a project with no claims', () => {
    const m = render(EMPTY);
    expect(m).toContain('No claims to verify yet');
    expect(m).toContain('Claims to verify');
    expect(m).toContain('Upload a project document or paste claim text');
    expect(m).toContain('Add the project boundary.');
    expect(m).toContain('Unavailable');
    expect(m).toContain('href="/app/acme/projects/proj-1/evidence"');
    expect(m).toContain('N/A');
    expect(m).not.toContain('Kariba');
    expect(m).not.toContain('Claims assessed');
    expect(m).not.toContain('Simulated');
  });
  it('shows the demo notice and a simulated chip for synthetic data', () => {
    const m = render({ ...EMPTY, data_mode: 'synthetic', is_demo: true, notice: 'Demonstration data for illustration.' });
    expect(m).toContain('data-data-mode="simulated"');
    expect(m).toContain('Demonstration data for illustration.');
    expect(m).toContain('Simulated');
  });
  it('renders real claims exactly as returned, with null-safe grading', () => {
    const m = render({ ...EMPTY, has_claims: true, total_claims: 1, overall_portfolio_grade: 'C', claims: [CLAIM] });
    expect(m).toContain('Area restored');
    expect(m).toContain('1,200 ha');
    expect(m).toContain('PARTIALLY SUPPORTED');
    expect(m).toContain('Area is 1200 ha');
    expect(m).toContain('Orthomosaic');
    expect(m).toContain('10 m pixels');
    expect(m).toContain('rationale one');
    expect(m).toContain('Portfolio grade C');
    expect(m).not.toContain('CAR-2026');
    expect(m).not.toContain('6f4a8b');
  });
  it('does not crash on a claim with only an id', () => {
    expect(() => render({ claims: [{ claim_id: 'only-id' }] })).not.toThrow();
  });
});
