import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { GroqIntelligenceWorkspace, ResearchResult } from '../src/components/panels/GroqIntelligenceWorkspace';
import { httpProblem, latencyLabel, researchBody, statusMessage, toResearch, toServiceStatus } from '../src/components/panels/intelligenceModel';

const html = (el: React.ReactElement) => renderToStaticMarkup(el);
const configured = { state: 'configured', model: 'm-1', provider: 'groq' } as const;
const projects = [{ id: 'uuid-1', name: 'Alpha', simulated: false }, { id: 'uuid-2', name: 'Beta', simulated: true }];

const OK = {
  project_id: 'uuid-1', query: 'q', mode: 'csr_due_diligence', stakeholder_role: null, model: 'm-1', status: 'ok', reason: null,
  latency_ms: 842.4, generated_at: '2026-01-01T00:00:00Z', data_mode: 'observed', answer: 'The boundary is registered.',
  retrieved_facts: [{ fact_id: 'F1', statement: 'Boundary hash recorded', source: 'project.boundary_sha256', kind: 'record', cited_by_model: true }],
  inferences: [{ statement: 'Likely complete', label: 'inference', based_on: ['F1'] }],
  unsupported_conclusions: ['Carbon stock cannot be concluded'],
  missing_context: ['No observations ingested'],
  published_literature: [{ kind: 'paper', title: 'Savanna regrowth', authors: 'A. Author', venue: 'J. Ecol', year: 2020, doi: '10.1/xyz', relevance: 'background' }],
  guardrail: { applied: true, notice: 'Restates records only.', dropped: [] },
};

describe('intelligence model', () => {
  it('maps service status', () => {
    expect(toServiceStatus({ status: 'configured', configured: true, model: 'm', provider: 'groq' })).toEqual({ state: 'configured', model: 'm', provider: 'groq' });
    expect(toServiceStatus({ status: 'unavailable', configured: false, reason: 'No key' })).toEqual({ state: 'unavailable', reason: 'No key' });
    expect(toServiceStatus(null).state).toBe('unavailable');
  });
  it('latency is only ever the measured value', () => {
    expect(latencyLabel(null)).toBeNull();
    expect(latencyLabel(842.4)).toBe('842 ms');
    expect(latencyLabel(2500)).toBe('2.50 s');
    expect(toResearch({ status: 'ok' }).latencyMs).toBeNull();
    expect(toResearch({ status: 'ok', latency_ms: 'fast' }).latencyMs).toBeNull();
    expect(toResearch({ status: 'ok', latency_ms: -3 }).latencyMs).toBeNull();
  });
  it('is safe on malformed bodies and unknown status becomes error', () => {
    for (const b of [null, 1, 'x', [], {}, { retrieved_facts: 'no', inferences: [null] }]) expect(() => toResearch(b)).not.toThrow();
    expect(toResearch({}).status).toBe('error');
  });
  it('builds the request body with a project id and only sends a role for stakeholder reports', () => {
    expect(researchBody(' hi there ', 'uuid-1', 'csr_due_diligence', 'csr')).toEqual({ query: 'hi there', project_id: 'uuid-1', mode: 'csr_due_diligence' });
    expect(researchBody('q q q', 'uuid-1', 'stakeholder_reports', 'auditor')).toMatchObject({ stakeholder_role: 'auditor' });
  });
  it('explains failures', () => {
    expect(statusMessage({ status: 'insufficient_context', reason: 'Nothing recorded' })).toBe('Nothing recorded');
    expect(statusMessage({ status: 'error', reason: '' })).toMatch(/error/);
    expect(httpProblem(429)).toMatch(/Too many/);
    expect(httpProblem(0)).toMatch(/could not be reached/);
  });
});

describe('GroqIntelligenceWorkspace', () => {
  it('shows an empty state with a create link and no sample answer when there are no projects', () => {
    const m = html(<GroqIntelligenceWorkspace orgSlug="acme" projects={[]} service={configured} />);
    expect(m).toContain('no project to ask about');
    expect(m).toContain('href="/app/acme/projects/new"');
    expect(m).not.toContain('Kariba');
    expect(m).not.toContain('184.2');
    expect(m).not.toContain('<form');
  });
  it('shows the unavailable reason first and disables the input', () => {
    const m = html(<GroqIntelligenceWorkspace orgSlug="acme" projects={projects} service={{ state: 'unavailable', reason: 'GROQ_API_KEY is not set.' }} />);
    expect(m).toContain('Intelligence service unavailable');
    expect(m).toContain('GROQ_API_KEY is not set.');
    expect(m).toMatch(/<input[^>]*disabled/);
    expect(m.indexOf('Intelligence service unavailable')).toBeLessThan(m.indexOf('intel-query'));
  });
  it('lists the org projects and the API modes', () => {
    const m = html(<GroqIntelligenceWorkspace orgSlug="acme" projects={projects} service={configured} />);
    expect(m).toContain('Alpha');
    expect(m).toContain('Beta (simulated)');
    expect(m).toContain('value="contradiction_detection"');
    expect(m).not.toContain('Groq LPU');
    expect(m).not.toMatch(/ ms Groq/);
  });
});

describe('ResearchResult states', () => {
  it('ok: three separate sections, measured latency, literature labelled as background', () => {
    const m = html(<ResearchResult result={toResearch(OK)} />);
    expect(m).toContain('Retrieved facts');
    expect(m).toContain('project.boundary_sha256');
    expect(m).toContain('Model inferences');
    expect(m).toContain('not records and not verified findings');
    expect(m).toContain('Cannot be concluded from the records');
    expect(m).toContain('Carbon stock cannot be concluded');
    expect(m).toContain('No observations ingested');
    expect(m).toContain('Measured response time');
    expect(m).toContain('842 ms');
    expect(m).toContain('Published literature (general background, not evidence about this project)');
    expect(m).toContain('https://doi.org/10.1/xyz');
  });
  it('latency null: no latency is shown', () => {
    const m = html(<ResearchResult result={toResearch({ ...OK, latency_ms: null })} />);
    expect(m).not.toContain('Measured response time');
    expect(m).not.toMatch(/\d+ ms/);
  });
  it('insufficient_context: shows the reason and no answer', () => {
    const m = html(<ResearchResult result={toResearch({ status: 'insufficient_context', reason: 'No records for this project.', latency_ms: null, answer: null, missing_context: ['Upload documents'] })} />);
    expect(m).toContain('Not enough project information');
    expect(m).toContain('No records for this project.');
    expect(m).toContain('Upload documents');
    expect(m).not.toContain('aria-label="Answer"');
  });
  it('unavailable and error: show status and reason, no answer or sections of invented content', () => {
    for (const status of ['unavailable', 'error'] as const) {
      const m = html(<ResearchResult result={toResearch({ status, reason: `reason-${status}`, latency_ms: null })} />);
      expect(m).toContain(`reason-${status}`);
      expect(m).toContain('No answer was produced');
      expect(m).not.toContain('Retrieved facts');
      expect(m).not.toContain('Measured response time');
    }
  });
});
