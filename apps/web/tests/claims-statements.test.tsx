import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { StatementList, UnclassifiedList } from '../src/features/claims/ClaimsWorkbench';
import type { ClaimsResponse } from '../src/features/claims/client';
import { formatStatementValue, highlightSpans, statementIndexForClaim, statementLabel, statementTone } from '../src/features/claims/statements';
import { segmentText } from '../src/features/claims/highlight';

const TEXT = 'Area is 12,000 hectares. We restored the whole region. Credits: 5,000 tCO2e. Nice weather.';
const DATA = {
  claims: [{ kind: 'area_hectares', value: 12000, unit: 'hectares', start: 8, end: 23, quote: '12,000 hectares', span: { start: 8, end: 23, text: '12,000 hectares' } }],
  comparisons: [{ claim_kind: 'area_hectares', claimed: 12000, estimated: null, note: 'No comparison' }],
  disclaimer: 'Screening aid.',
  statements: [
    { statement_id: 's1', kind: 'area_hectares', status: 'extracted', text: 'Area is 12,000 hectares.', span: { start: 0, end: 24, text: 'Area is 12,000 hectares.' }, value: 12000, unit: 'hectares', period: null, reason: 'Read from the text.', evidence_link: null, evidence_gap: 'No boundary uploaded.' },
    { statement_id: 's2', kind: 'overclaim', status: 'overclaim', text: 'We restored the whole region.', span: { start: 25, end: 54, text: 'We restored the whole region.' }, value: null, unit: null, period: '2020-2023', reason: 'Sweeping claim without a figure.', evidence_link: null, evidence_gap: 'Needs a measured area.' },
    { statement_id: 's3', kind: 'credits_issued', status: 'unsupported_by_available_evidence', text: 'Credits: 5,000 tCO2e.', span: { start: 55, end: 76, text: 'Credits: 5,000 tCO2e.' }, value: 5000, unit: 'tCO2e', period: null, reason: 'No registry record.', evidence_link: null, evidence_gap: 'No issuance record.' },
  ],
  unrecognised_sentences: [{ start: 77, end: 89, text: 'Nice weather.' }],
} as unknown as ClaimsResponse;

describe('statement model', () => {
  it('tones: overclaim flagged, unsupported neutral, extracted accent', () => {
    expect(statementTone('overclaim')).toBe('danger');
    expect(statementTone('unsupported_by_available_evidence')).toBe('neutral');
    expect(statementTone('extracted')).toBe('accent');
  });
  it('never labels extraction as verification', () => {
    expect(statementLabel('extracted')).toMatch(/not verified/);
    expect(statementLabel('overclaim')).toMatch(/overclaim/i);
  });
  it('formats value, unit and period without inventing parts', () => {
    expect(formatStatementValue({ value: 12000, unit: 'hectares', period: null })).toBe('12,000 hectares');
    expect(formatStatementValue({ value: null, unit: null, period: '2020-2023' })).toBe('2020-2023');
    expect(formatStatementValue({ value: null, unit: null, period: null })).toBe('');
  });
  it('highlights every statement span and round-trips the text', () => {
    const spans = highlightSpans(DATA);
    expect(spans).toHaveLength(3);
    const segs = segmentText(TEXT, spans);
    expect(segs.map((s) => s.text).join('')).toBe(TEXT);
    expect(segs.filter((s) => s.claim !== null)).toHaveLength(3);
  });
  it('falls back to claim spans for an older response without statements', () => {
    const old = { ...DATA, statements: undefined } as unknown as ClaimsResponse;
    expect(highlightSpans(old)).toHaveLength(1);
    expect(statementIndexForClaim(old, 0)).toBe(0);
  });
  it('maps a claim to the statement that contains it', () => {
    expect(statementIndexForClaim(DATA, 0)).toBe(0);
  });
});

describe('statement rendering', () => {
  const m = renderToStaticMarkup(<StatementList data={DATA} />);
  it('shows every statement with text, value, status, reason and gap', () => {
    expect((m.match(/data-statement-status=/g) ?? []).length).toBe(3);
    expect(m).toContain('Area is 12,000 hectares.');
    expect(m).toContain('12,000 hectares');
    expect(m).toContain('2020-2023');
    expect(m).toContain('Sweeping claim without a figure.');
    expect(m).toContain('Needs a measured area.');
    expect(m).toContain('Possible overclaim');
    expect(m).toContain('Not supported by available evidence');
    expect(m).toContain('Extracted from text, not verified');
  });
  it('lists unrecognised sentences under their own heading', () => {
    const u = renderToStaticMarkup(<UnclassifiedList data={DATA} />);
    expect(u).toContain('Sentences we could not classify');
    expect(u).toContain('Nice weather.');
  });
  it('renders nothing extra when there are none', () => {
    expect(renderToStaticMarkup(<UnclassifiedList data={{ ...DATA, unrecognised_sentences: [] }} />)).toBe('');
    expect(renderToStaticMarkup(<StatementList data={{ ...DATA, statements: [] }} />)).toBe('');
  });
});
