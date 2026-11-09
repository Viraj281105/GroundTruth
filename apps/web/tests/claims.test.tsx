import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }), usePathname: () => '/x' }));

import { ClaimVerificationWorkbench } from '../src/components/panels/ClaimVerificationWorkbench';
import { toPortfolio } from '../src/components/panels/claimWorkbenchModel';
import { CandidateList } from '../src/features/projects/CandidateList';
import { ClaimForm } from '../src/features/projects/ClaimForm';
import { createClaim, listClaims, patchClaim, withdrawClaim } from '../src/features/projects/claims.client';
import {
  candidateStatusCopy,
  claimErrorMessage,
  correctionNotice,
  emptyForm,
  formFromCandidate,
  isPromoted,
  outcomeCopy,
  validateClaimForm,
  type ClaimCandidate,
  type ClaimKindView,
  type ClaimSource,
  type ProjectClaimView,
} from '../src/features/projects/claims.model';

const html = (el: React.ReactElement) => renderToStaticMarkup(el);
const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

const KINDS: ClaimKindView[] = [
  { kind: 'area_hectares', label: 'Area restored', checkable: true, note: 'Compared with the project boundary area.' },
  { kind: 'survival_rate', label: 'Tree survival', checkable: false, note: 'Satellite greenness cannot show survival.' },
];

const SOURCE: ClaimSource = {
  project_claim_id: 'pc1',
  document_id: 'd1',
  document_name: 'design.txt',
  document_sha256: 'abc',
  start: 10,
  end: 60,
  original_text: 'We restored 1,200 hectares between 2019 and 2023.',
  original_kind: 'area_hectares',
  original_value: 1200,
  original_unit: 'ha',
  original_period: '2019-2023',
  statement_text: 'We restored 1,200 hectares between 2019 and 2023.',
  kind: 'area_hectares',
  value: 1200,
  unit: 'ha',
  period: '2019-2023',
  edited: false,
  created_at: null,
  updated_at: null,
};

const cand = (over: Partial<ClaimCandidate> = {}): ClaimCandidate => ({
  kind: 'area_hectares',
  value: 1200,
  unit: 'ha',
  start: 10,
  end: 60,
  quote: 'We restored 1,200 hectares.',
  period: '2019-2023',
  status: 'extracted',
  reason: null,
  evidence_gap: null,
  ...over,
});

const pc = (source: ClaimSource = SOURCE): ProjectClaimView => ({
  id: 'pc1',
  kind_label: 'Area restored',
  checkable: true,
  source,
  outcome: {
    status: 'UNVERIFIED',
    headline: 'x',
    reasons: [],
    supporting: [],
    contradicting: [],
    required_evidence: [],
    available_evidence: [],
    missing_evidence: [],
    limitations: [],
    observed_value: null,
    observed_unit: null,
    discrepancy_percentage: null,
    methodology: '',
  },
});

describe('outcomeCopy', () => {
  it('uses the plain labels', () => {
    expect(outcomeCopy('SUPPORTED').label).toBe('Consistent with the evidence');
    expect(outcomeCopy('PARTIALLY_SUPPORTED').label).toBe('Partly consistent');
    expect(outcomeCopy('CONTRADICTED').label).toBe('Evidence points the other way');
    expect(outcomeCopy('UNVERIFIED').label).toBe('Not enough evidence to test');
  });
  it('never presents UNVERIFIED as false, and unknown statuses fall to not-enough-evidence', () => {
    expect(outcomeCopy('UNVERIFIED').plain).toContain('does not mean the claim is false');
    expect(outcomeCopy('weird').label).toBe('Not enough evidence to test');
    expect(outcomeCopy('CONTRADICTED').plain).not.toMatch(/fraud|false claim/i);
  });
});

describe('candidateStatusCopy', () => {
  it('labels an overclaim and never calls a candidate verified', () => {
    expect(candidateStatusCopy('overclaim').label).toBe('Goes further than evidence can show');
    expect(candidateStatusCopy('unsupported_by_available_evidence').label).toContain('No evidence');
    expect(candidateStatusCopy(null).label).toBe('Found in the text');
  });
});

describe('isPromoted', () => {
  it('matches on document and exact span only', () => {
    expect(isPromoted('d1', { start: 10, end: 60 }, [pc()])).toBe(true);
    expect(isPromoted('d2', { start: 10, end: 60 }, [pc()])).toBe(false);
    expect(isPromoted('d1', { start: 10, end: 61 }, [pc()])).toBe(false);
    expect(isPromoted('d1', { start: null, end: null }, [pc({ ...SOURCE, start: null, end: null })])).toBe(false);
  });
});

describe('validateClaimForm', () => {
  const ok = { statement: 'Area restored was 1200 hectares', kind: 'area_hectares', value: '1,200', unit: 'ha', period: '2019-2023' };
  it('accepts a good form and returns clean fields', () => {
    const r = validateClaimForm(ok, KINDS);
    expect(r).toEqual({ ok: true, fields: { statement_text: 'Area restored was 1200 hectares', kind: 'area_hectares', value: 1200, unit: 'ha', period: '2019-2023' } });
  });
  it('allows no number, unit or period', () => {
    const r = validateClaimForm({ ...ok, value: '', unit: ' ', period: '' }, KINDS);
    expect(r.ok && r.fields).toMatchObject({ value: null, unit: null, period: null });
  });
  it('rejects short and long statements', () => {
    expect(validateClaimForm({ ...ok, statement: ' a  b ' }, KINDS)).toMatchObject({ ok: false, errors: { statement: expect.stringContaining('at least 5') } });
    expect(validateClaimForm({ ...ok, statement: 'x'.repeat(1001) }, KINDS)).toMatchObject({ ok: false, errors: { statement: expect.stringContaining('at most 1000') } });
    expect(validateClaimForm({ ...ok, statement: 'x'.repeat(1000) }, KINDS).ok).toBe(true);
  });
  it('requires a kind from the list', () => {
    expect(validateClaimForm({ ...ok, kind: '' }, KINDS)).toMatchObject({ ok: false, errors: { kind: expect.any(String) } });
    expect(validateClaimForm({ ...ok, kind: 'made_up' }, KINDS)).toMatchObject({ ok: false, errors: { kind: expect.stringContaining('not one of') } });
  });
  it('requires a numeric value and limits unit and period', () => {
    expect(validateClaimForm({ ...ok, value: 'twelve' }, KINDS)).toMatchObject({ ok: false, errors: { value: expect.any(String) } });
    expect(validateClaimForm({ ...ok, value: 'Infinity' }, KINDS)).toMatchObject({ ok: false });
    expect(validateClaimForm({ ...ok, unit: 'u'.repeat(41) }, KINDS)).toMatchObject({ ok: false, errors: { unit: expect.any(String) } });
    expect(validateClaimForm({ ...ok, period: 'p'.repeat(61) }, KINDS)).toMatchObject({ ok: false, errors: { period: expect.any(String) } });
  });
  it('prefills from a candidate', () => {
    expect(formFromCandidate(cand())).toEqual({ statement: 'We restored 1,200 hectares.', kind: 'area_hectares', value: '1200', unit: 'ha', period: '2019-2023' });
    expect(emptyForm().kind).toBe('');
  });
});

describe('claimErrorMessage', () => {
  const body = (code: string, message: string, hint?: string) => ({ detail: { code, message, hint } });
  it('shows the API message and hint as sent', () => {
    expect(claimErrorMessage(409, body('already_promoted', 'Already a claim.', 'Open Verification.'))).toBe('Already a claim. Open Verification.');
  });
  it('has wording for every documented code when the message is missing', () => {
    for (const code of ['already_promoted', 'source_not_found', 'document_not_readable', 'too_many_claims', 'invalid_claim']) {
      expect(claimErrorMessage(409, { detail: { code } })).not.toMatch(/HTTP/);
    }
  });
  it('falls back to status wording', () => {
    expect(claimErrorMessage(0, null)).toContain('could not be reached');
    expect(claimErrorMessage(403, {})).toContain('does not allow');
    expect(claimErrorMessage(404, null)).toContain('not found');
    expect(claimErrorMessage(500, null)).toContain('HTTP 500');
  });
});

describe('correctionNotice', () => {
  it('is null when nothing was edited', () => expect(correctionNotice(SOURCE)).toBeNull());
  it('says what the document said and what is tested', () => {
    const n = correctionNotice({ ...SOURCE, edited: true, value: 120, statement_text: 'We restored 120 hectares between 2019 and 2023.' });
    expect(n).toContain('You corrected this');
    expect(n).toContain('the document said 1,200 ha (2019-2023), tested as 120 ha (2019-2023)');
    expect(n).toContain('the wording was changed');
  });
});

describe('claims client', () => {
  it('lists with credentials and returns data', async () => {
    const f = vi.fn().mockResolvedValue(res(200, { project_id: 'p', claims: [], kinds: [], note: '' }));
    const r = await listClaims('p/1', f);
    expect(r.ok).toBe(true);
    expect(f.mock.calls[0][0]).toMatch(/\/projects\/p%2F1\/claims$/);
    expect(f.mock.calls[0][1]).toMatchObject({ credentials: 'include' });
  });
  it('POSTs json, PATCHes, DELETEs (204)', async () => {
    const f = vi.fn().mockResolvedValueOnce(res(201, pc())).mockResolvedValueOnce(res(200, pc())).mockResolvedValueOnce(res(204));
    expect((await createClaim('p', { document_id: 'd1', start: 1, end: 2 }, f)).ok).toBe(true);
    expect(f.mock.calls[0][1]).toMatchObject({ method: 'POST', credentials: 'include', body: JSON.stringify({ document_id: 'd1', start: 1, end: 2 }) });
    expect((await patchClaim('p', 'c1', { value: 5 }, f)).ok).toBe(true);
    expect(f.mock.calls[1][1]).toMatchObject({ method: 'PATCH' });
    expect(f.mock.calls[1][0]).toMatch(/claims\/c1$/);
    expect(await withdrawClaim('p', 'c1', f)).toEqual({ ok: true, data: null });
    expect(f.mock.calls[2][1]).toMatchObject({ method: 'DELETE' });
  });
  it('maps API errors with code, and network failures', async () => {
    const f = vi.fn().mockResolvedValue(res(409, { detail: { code: 'already_promoted', message: 'Already a claim.', hint: 'Edit it instead.' } }));
    expect(await createClaim('p', {}, f)).toMatchObject({ ok: false, status: 409, code: 'already_promoted', message: 'Already a claim. Edit it instead.' });
    const g = vi.fn().mockRejectedValue(new Error('down'));
    expect(await withdrawClaim('p', 'c', g)).toMatchObject({ ok: false, status: 0 });
  });
});

describe('ClaimForm', () => {
  it('is prefilled and shows the kind note, including when a type cannot be checked', () => {
    const m = html(<ClaimForm initial={{ ...formFromCandidate(cand()), kind: 'survival_rate' }} kinds={KINDS} submitLabel="Add as claim" onSubmit={() => undefined} onCancel={() => undefined} />);
    expect(m).toContain('We restored 1,200 hectares.');
    expect(m).toContain('value="1200"');
    expect(m).toContain('Satellite greenness cannot show survival.');
    expect(m).toContain('no check for this type');
    expect(m).toContain('Add as claim');
  });
});

describe('CandidateList', () => {
  const base = { documentId: 'd1', kinds: KINDS, verificationHref: '/app/o/projects/p/verification', blockedReason: null };
  it('shows quote, figure, status, reason, evidence gap and a review button for editors', () => {
    const m = html(<CandidateList {...base} canEdit claims={[]} candidates={[cand({ status: 'overclaim', reason: 'Greenness is not survival.', evidence_gap: 'Field survey' })]} />);
    expect(m).toContain('Area restored');
    expect(m).toContain('1200 ha');
    expect(m).toContain('We restored 1,200 hectares.');
    expect(m).toContain('Goes further than evidence can show');
    expect(m).toContain('Not verified');
    expect(m).toContain('Greenness is not survival.');
    expect(m).toContain('What is missing: Field survey');
    expect(m).toContain('Review and add as claim');
  });
  it('marks an already-promoted candidate and offers no add button', () => {
    const m = html(<CandidateList {...base} canEdit claims={[pc()]} candidates={[cand()]} />);
    expect(m).toContain('Already a claim');
    expect(m).not.toContain('Review and add as claim');
    expect(m).toContain('href="/app/o/projects/p/verification"');
  });
  it('shows Added to claims with a link right after promotion', () => {
    const m = html(<CandidateList {...base} canEdit claims={[]} justAdded={['10-60']} candidates={[cand()]} />);
    expect(m).toContain('Added to claims');
    expect(m).toContain('See it on the Verification page');
  });
  it('is read-only for a viewer: explains and offers no button', () => {
    const m = html(<CandidateList {...base} canEdit={false} blockedReason="Your role is read-only." claims={[]} candidates={[cand()]} />);
    expect(m).toContain('Your role is read-only.');
    expect(m).not.toContain('Review and add as claim');
  });
  it('offers no add button when claims could not be loaded', () => {
    const m = html(<CandidateList {...base} canEdit claims={null} candidates={[cand()]} />);
    expect(m).not.toContain('Review and add as claim');
    expect(m).toContain('could not be loaded');
  });
});

const raw = (over: Record<string, unknown> = {}) => ({
  claim_id: 'pc1',
  claim_type: 'area_restored',
  title: 'Area restored',
  claimed_value: 1200,
  claimed_unit: 'ha',
  status: 'UNVERIFIED',
  headline: 'Not enough evidence to test this claim.',
  reasons: ['No project boundary has been uploaded.'],
  supporting_observations: [],
  contradictory_observations: [],
  required_evidence: ['Project boundary'],
  available_evidence: [],
  missing_evidence: ['Project boundary'],
  verification_methodology: 'Compared with boundary area.',
  confidence_and_limitations: ['Greenness cannot show survival.'],
  decomposed_statements: [],
  source: SOURCE,
  ...over,
});
const wb = (claims: unknown[], extra: Partial<React.ComponentProps<typeof ClaimVerificationWorkbench>> = {}) =>
  html(
    <ClaimVerificationWorkbench
      projectName="P"
      orgSlug="acme"
      projectSlug="proj"
      portfolio={toPortfolio({ claims, has_claims: claims.length > 0, data_mode: 'observed', is_demo: false })}
      {...extra}
    />,
  );

describe('workbench with promoted claims', () => {
  it('renders every outcome with its plain label', () => {
    const m = wb(
      (['SUPPORTED', 'PARTIALLY_SUPPORTED', 'CONTRADICTED', 'UNVERIFIED'] as const).map((s, i) => raw({ claim_id: `c${i}`, status: s })),
    );
    expect(m).toContain('CONSISTENT WITH THE EVIDENCE');
    expect(m).toContain('PARTLY CONSISTENT');
    expect(m).toContain('EVIDENCE POINTS THE OTHER WAY');
    expect(m).toContain('NOT ENOUGH EVIDENCE TO TEST');
  });
  it('shows UNVERIFIED reasons, what is missing and limitations, without saying false', () => {
    const m = wb([raw()]);
    expect(m).toContain('Not enough evidence to test this claim.');
    expect(m).toContain('No project boundary has been uploaded.');
    expect(m).toContain('Project boundary');
    expect(m).toContain('Greenness cannot show survival.');
    expect(m).toContain('does not mean the claim is false');
    expect(m).not.toContain('EV. QUAL');
  });
  it('shows where it came from: document name and the original quote', () => {
    const m = wb([raw()]);
    expect(m).toContain('Where this claim came from');
    expect(m).toContain('design.txt');
    expect(m).toContain('We restored 1,200 hectares between 2019 and 2023.');
    expect(m).not.toContain('You corrected this');
  });
  it('shows what was corrected, beside what the document said', () => {
    const m = wb([raw({ source: { ...SOURCE, edited: true, value: 120, statement_text: 'We restored 120 hectares between 2019 and 2023.' } })]);
    expect(m).toContain('You corrected this');
    expect(m).toContain('the document said 1,200 ha (2019-2023), tested as 120 ha (2019-2023)');
    expect(m).toContain('Now tested as');
    expect(m).toContain('We restored 1,200 hectares between 2019 and 2023.');
  });
  it('shows typed claims as typed, not as from a document', () => {
    const m = wb([raw({ source: { ...SOURCE, document_id: null, document_name: null } })]);
    expect(m).toContain('Typed in by a team member');
  });
  it('keeps the existing display for claims without a source', () => {
    const m = wb([raw({ source: undefined, headline: undefined, reasons: undefined, grading: { evidence_quality_grade: 'C', overall_grade: 'C' } })]);
    expect(m).not.toContain('Where this claim came from');
    expect(m).toContain('EV. QUAL');
    expect(m).toContain('UNVERIFIED');
  });
  it('gives editors Edit, Withdraw and the typing form; viewers get an explanation instead', () => {
    const editor = wb([raw()], { projectId: 'p1', canEdit: true, kinds: KINDS });
    expect(editor).toContain('>Edit<');
    expect(editor).toContain('>Withdraw<');
    expect(editor).toContain('Add a claim by typing it');
    const viewer = wb([raw()], { projectId: 'p1', canEdit: false, kinds: KINDS });
    expect(viewer).not.toContain('>Edit<');
    expect(viewer).not.toContain('>Withdraw<');
    expect(viewer).not.toContain('Add a claim by typing it');
    expect(viewer).toContain('data-claim-readonly');
  });
  it('empty state points to the Evidence tab and typing a claim', () => {
    const m = wb([], { projectId: 'p1', canEdit: true, kinds: KINDS });
    expect(m).toContain('No claims to verify yet');
    expect(m).toContain('promoting');
    expect(m).toContain('href="/app/acme/projects/proj/evidence"');
    expect(m).toContain('Add a claim by typing it');
    expect(m).not.toContain('Claims assessed');
  });
});
