import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { MOCK_CASE_DETAILS, MOCK_VERIFICATION_RESULTS } from '../src/lib/fixtures/simulated-data';
import { findEvidence, numberValue } from '../src/lib/evidence';
import { buildOverviewModel } from '../src/features/case/overview/model';
import { OverviewView } from '../src/features/case/overview/OverviewView';
import { ReportView } from '../src/features/case/report/ReportView';
import { EvidenceScope, SourceBanner, VizLimitation } from '../src/features/case/evidence/EvidenceProvenance';
import { chooseEvidenceSource, EVIDENCE_SCOPE, RECONCILIATION, SOURCE_COPY } from '../src/features/case/evidence/provenance';
import { evidenceHref } from '../src/features/run/RunFlow';
import { createCase } from '../src/features/cases/create-case';
import { exportUrl, fetchReportFile, filenameFrom, validateExport } from '../src/features/case/report/downloads';

const root = join(__dirname, '..', 'src');
const read = (p: string) => readFileSync(join(root, p), 'utf8');

const enc = (s: string) => new TextEncoder().encode(s);
const PDF = enc('%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n');
const CSV = enc('evidence_id,value\neffect.point_estimate,0.0547\n');

function resp(body: Uint8Array | string, init: { status?: number; headers?: Record<string, string> } = {}): Response {
  const data = typeof body === 'string' ? enc(body) : body;
  return new Response(data as unknown as BodyInit, { status: init.status ?? 200, headers: init.headers });
}

describe('evidence source precedence', () => {
  it('a named run always beats the precomputed fixture', () => {
    expect(chooseEvidenceSource('run_abc', true)).toBe('fresh-run');
    expect(chooseEvidenceSource('run_abc', false)).toBe('fresh-run');
  });
  it('uses the fixture only when no run is named', () => {
    expect(chooseEvidenceSource(null, true)).toBe('precomputed-fixture');
    expect(chooseEvidenceSource(null, false)).toBe('none');
  });
  it('the hook uses that rule, never lets the fixture answer for a run, and draws no series for a run', () => {
    const src = read('features/case/evidence/useCaseEvidence.ts');
    expect(src).toContain('chooseEvidenceSource(runId');
    expect(src).toMatch(/viz: null, isDemo: false, runId, origin: 'fresh-run'/);
    expect(src).toMatch(/viz: fixture, isDemo: true, runId: null, origin: 'precomputed-fixture'/);
  });
  it('the run flow links to the evidence of the run that just finished', () => {
    expect(evidenceHref('kariba-redd', 'run_x1')).toBe('/cases/kariba-redd/evidence?run=run_x1');
    expect(evidenceHref('kariba-redd', null)).toBe('/cases/kariba-redd/evidence');
  });
});

describe('source labelling', () => {
  it('labels the precomputed fixture as a synthetic benchmark', () => {
    const html = renderToStaticMarkup(<SourceBanner origin="precomputed-fixture" runId={null} />);
    expect(html).toContain('Synthetic benchmark');
    expect(html).toContain('precomputed');
    expect(html).toContain('not a satellite observation');
    expect(html).toContain('data-evidence-origin="precomputed-fixture"');
  });
  it('labels a fresh run as derived, names it, and denies live ingestion', () => {
    const html = renderToStaticMarkup(<SourceBanner origin="fresh-run" runId="run_42" />);
    expect(html).toContain('run_42');
    expect(html).toContain('Derived analysis');
    expect(html).toContain('not live satellite ingestion');
  });
  it('explains the missing series for a fresh run instead of inventing them', () => {
    const html = renderToStaticMarkup(<VizLimitation />);
    expect(html).toContain('counterfactual path');
    expect(html).toContain('placebo distribution');
    expect(html).toContain('nothing has been substituted');
  });
  it('the evidence view never draws a counterfactual or placebo from a run without series', () => {
    const src = read('features/case/evidence/EvidenceView.tsx');
    expect(src).toMatch(/viz && caseDetail \? \(\s*<CounterfactualChart/);
    expect(src).toMatch(/viz \? \(\s*<BinnedHistogram/);
    expect(src).toContain("origin === 'fresh-run' && <VizLimitation />");
  });
  it('keeps the fixture available in demo mode', () => {
    expect(MOCK_VERIFICATION_RESULTS['kariba-redd']).toBeTruthy();
  });
});

describe('evidence scope statements', () => {
  const html = renderToStaticMarkup(<EvidenceScope caseId="kariba-redd" withReconciliation />);
  it('separates real observations, the synthetic panel, and what is not claimed', () => {
    expect(html).toContain('Sentinel-2 L2A zonal composites for Kariba, 2021-2023');
    expect(html).toContain('Kariba plus donors, 2001-2022');
    expect(html).toContain('CHIRPS rainfall and NASA POWER');
    expect(html).toContain('not yet part of the primary verification API');
    expect(html).toContain('Carbon impact is not calibrated');
    expect(html).toContain('Causal attribution is inconclusive');
    expect(html).toContain('not combined into an observed causal analysis');
  });
  it('does not make Kariba claims on another case', () => {
    const other = renderToStaticMarkup(<EvidenceScope caseId="mikoko-pamoja" />);
    expect(other).not.toContain('Sentinel-2');
    expect(other).not.toContain('CHIRPS');
    expect(other).toContain('No real satellite or climate observations');
    expect(other).toContain('Carbon impact is not calibrated');
  });
  it('has exactly one scope row per required distinction', () => {
    expect(EVIDENCE_SCOPE).toHaveLength(6);
  });
});

describe('metric reconciliation', () => {
  const fixture = MOCK_VERIFICATION_RESULTS['kariba-redd'];
  it('the on-screen headline is the precomputed fixture value and it is positive', () => {
    const v = numberValue(findEvidence(fixture.verification.bundle.items, 'effect.point_estimate'));
    expect(v).toBeGreaterThan(0.0547);
    expect(v).toBeLessThan(0.0548);
    expect(RECONCILIATION.find((r) => r.id === 'headline')?.explanation).toContain('-0.0547');
  });
  it('documents 37, 50 and 80 as different pools', () => {
    const d = RECONCILIATION.find((r) => r.id === 'donors')!;
    expect(d.value).toBe('37 / 50 / 80');
    expect(d.explanation).toMatch(/not stale copies/);
    expect(numberValue(findEvidence(fixture.verification.bundle.items, 'matching.n_donors_admitted'))).toBe(50);
    expect(MOCK_CASE_DETAILS['kariba-redd'].donor_pool_size).toBe(80);
  });
  it('documents the 0.04158 / 0.04156 pair as a separate panel', () => {
    expect(RECONCILIATION.find((r) => r.id === 'causal')?.value).toBe('+0.04158 / +0.04156');
  });
  it('the verdict stays inconclusive and is labelled a synthetic benchmark on the overview', () => {
    expect(fixture.verification.bundle.verdict?.label).toBe('inconclusive');
    const model = buildOverviewModel(MOCK_CASE_DETAILS['kariba-redd'], fixture, null);
    const html = renderToStaticMarkup(<OverviewView caseId="kariba-redd" model={model} />);
    expect(model.verdictLabel).toBe('inconclusive');
    expect(html).toContain('Synthetic benchmark');
    expect(html).toContain('Inconclusive');
    expect(html).toContain('Configured candidate pool');
    expect(html).not.toContain('>Donor pool size<');
  });
});

describe('case creation sends the session cookie', () => {
  it('uses credentials: include, and the form goes through that helper', () => {
    expect(read('features/cases/create-case.ts')).toContain("credentials: 'include'");
    expect(read('features/cases/NewCaseForm.tsx')).toContain('createCase(payload)');
  });
  it('POSTs /cases with credentials included and returns the case id', async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify({ case_id: 'c-1' }), { status: 201 }));
    const r = await createCase({ name: 'x' }, f);
    expect(r).toEqual({ ok: true, caseId: 'c-1' });
    const [url, init] = f.mock.calls[0];
    expect(String(url)).toMatch(/\/cases$/);
    expect(init.credentials).toBe('include');
    expect(init.method).toBe('POST');
  });
  it('reports a 401 as not signed in, never as success', async () => {
    const r = await createCase({}, vi.fn().mockResolvedValue(new Response('{"detail":"Not authenticated"}', { status: 401 })));
    expect(r).toMatchObject({ ok: false, reason: 'unauthenticated' });
  });
  it('turns a validation list into readable text', async () => {
    const body = JSON.stringify({ detail: [{ msg: 'area must be positive' }, { msg: 'name too short' }] });
    const r = await createCase({}, vi.fn().mockResolvedValue(new Response(body, { status: 422 })));
    expect(r).toEqual({ ok: false, reason: 'rejected', message: 'area must be positive; name too short' });
  });
  it('reports an unreachable API', async () => {
    const r = await createCase({}, vi.fn().mockRejectedValue(new TypeError('fetch failed')));
    expect(r).toMatchObject({ ok: false, reason: 'network' });
  });
});

describe('report downloads', () => {
  it('shows both download actions on the report', () => {
    const model = buildOverviewModel(MOCK_CASE_DETAILS['kariba-redd'], MOCK_VERIFICATION_RESULTS['kariba-redd'], null);
    const html = renderToStaticMarkup(
      <ReportView caseId="kariba-redd" report={{ markdown: '# r', generator: 'deterministic', citation: 'c', overview: model }} />,
    );
    expect(html).toContain('Download PDF');
    expect(html).toContain('Download CSV');
    expect(html).toContain('Synthetic benchmark');
  });
  it('offers the downloads even before any report exists', () => {
    const html = renderToStaticMarkup(<ReportView caseId="kariba-redd" report={null} />);
    expect(html).toContain('Download PDF');
  });
  it('targets the existing backend endpoints', () => {
    expect(exportUrl('kariba-redd', 'pdf')).toMatch(/\/cases\/kariba-redd\/export\/pdf$/);
    expect(exportUrl('kariba-redd', 'csv')).toMatch(/\/cases\/kariba-redd\/export\/csv$/);
  });
  it('accepts a real PDF and sends cookies', async () => {
    const f = vi.fn().mockResolvedValue(
      resp(PDF, { headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="kariba-redd-report.pdf"', 'X-GroundTruth-Data-Mode': 'simulated' } }),
    );
    const r = await fetchReportFile('kariba-redd', 'pdf', f);
    expect(f.mock.calls[0][1].credentials).toBe('include');
    expect(r).toMatchObject({ ok: true, filename: 'kariba-redd-report.pdf', dataMode: 'simulated' });
    if (r.ok) expect(r.bytes).toBe(PDF.byteLength);
  });
  it('rejects a 200 that is not a PDF', async () => {
    const r = await fetchReportFile('kariba-redd', 'pdf', vi.fn().mockResolvedValue(resp('<html>login</html>')));
    expect(r).toMatchObject({ ok: false, kind: 'invalid_file' });
  });
  it('rejects a truncated PDF and an empty file', async () => {
    expect(validateExport('pdf', enc('%PDF-1.4\n1 0 obj'))).toMatch(/incomplete/);
    expect(validateExport('pdf', new Uint8Array())).toMatch(/empty/);
  });
  it('accepts a CSV with rows and rejects a header-only or HTML one', async () => {
    expect(validateExport('csv', CSV)).toBeNull();
    expect(validateExport('csv', enc('a,b\n'))).toMatch(/no data rows/);
    expect(validateExport('csv', enc('<html><body>x</body></html>'))).toMatch(/web page/);
  });
  it.each([
    [401, 'unauthenticated'],
    [403, 'forbidden'],
    [404, 'not_found'],
    [500, 'server'],
  ])('maps HTTP %i to %s', async (status, kind) => {
    const r = await fetchReportFile('kariba-redd', 'csv', vi.fn().mockResolvedValue(resp('x', { status })));
    expect(r).toMatchObject({ ok: false, kind });
  });
  it('maps an unreachable service to a network failure', async () => {
    const r = await fetchReportFile('kariba-redd', 'pdf', vi.fn().mockRejectedValue(new TypeError('x')));
    expect(r).toMatchObject({ ok: false, kind: 'network' });
  });
  it('falls back to a predictable filename', () => {
    expect(filenameFrom(null, 'kariba-redd', 'pdf')).toBe('kariba-redd-report.pdf');
    expect(filenameFrom(null, 'kariba-redd', 'csv')).toBe('kariba-redd-evidence.csv');
    expect(filenameFrom('attachment; filename="../evil.csv"', 'k', 'csv')).not.toContain('/');
  });
});

describe('copy honesty', () => {
  it('never describes the synthetic run as live ingestion', () => {
    expect(SOURCE_COPY.freshBody).toContain('not live satellite ingestion');
    expect(read('features/run/copy.ts')).toContain('not live satellite ingestion');
  });
});
