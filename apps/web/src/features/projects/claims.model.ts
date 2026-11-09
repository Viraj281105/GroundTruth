import type { Schemas } from '../../lib/api-client';

export type ProjectClaimView = Schemas['ClaimView'];
export type ClaimListView = Schemas['ClaimListView'];
export type ClaimKindView = Schemas['KindView'];
export type ClaimCandidate = Schemas['ClaimCandidate'];
export type ClaimSource = Schemas['ClaimSourceView'];
export type ClaimOutcome = Schemas['ClaimOutcomeView'];
export type OutcomeStatus = ClaimOutcome['status'];
export type ClaimCreateBody = Schemas['ClaimCreate'];
export type ClaimPatchBody = Schemas['ClaimPatch'];

export type Tone = 'neutral' | 'accent' | 'caution' | 'danger';

export const STATEMENT_MIN = 5;
export const STATEMENT_MAX = 1000;
export const UNIT_MAX = 40;
export const PERIOD_MAX = 60;

export interface OutcomeCopy {
  label: string;
  tone: Tone;
  plain: string;
}

/** What each outcome means in plain words. UNVERIFIED is "not enough evidence", never "false". */
export function outcomeCopy(status: OutcomeStatus | string): OutcomeCopy {
  switch (status) {
    case 'SUPPORTED':
      return { label: 'Consistent with the evidence', tone: 'accent', plain: 'The evidence on file does not conflict with this claim. That is not proof the claim is true.' };
    case 'PARTIALLY_SUPPORTED':
      return { label: 'Partly consistent', tone: 'caution', plain: 'Some of the evidence agrees with this claim and some does not, or only part of it could be tested.' };
    case 'CONTRADICTED':
      return { label: 'Evidence points the other way', tone: 'danger', plain: 'The evidence on file disagrees with this claim. The reasons below say how. It calls for review, not a conclusion about anyone.' };
    default:
      return { label: 'Not enough evidence to test', tone: 'neutral', plain: 'The evidence needed to test this claim has not been supplied, or is of a kind that cannot establish it. This does not mean the claim is false.' };
  }
}

export interface CandidateCopy {
  label: string;
  tone: Tone;
}

/** Candidate statuses describe what the platform could ever check, not whether the statement is right. */
export function candidateStatusCopy(status: string | null | undefined): CandidateCopy {
  switch (status) {
    case 'overclaim':
      return { label: 'Goes further than evidence can show', tone: 'caution' };
    case 'unsupported_by_available_evidence':
      return { label: 'No evidence on file to test it', tone: 'neutral' };
    default:
      return { label: 'Found in the text', tone: 'accent' };
  }
}

const sameSpan = (a: number | null | undefined, b: number | null | undefined) => typeof a === 'number' && a === b;

/** True when a project claim already exists for this exact span of this document. */
export function isPromoted(documentId: string, c: Pick<ClaimCandidate, 'start' | 'end'>, claims: readonly Pick<ProjectClaimView, 'source'>[]): boolean {
  return claims.some((x) => x.source.document_id === documentId && sameSpan(x.source.start, c.start) && sameSpan(x.source.end, c.end));
}

/* ---- form ---- */

export interface ClaimFormState {
  statement: string;
  kind: string;
  value: string;
  unit: string;
  period: string;
}

export const emptyForm = (): ClaimFormState => ({ statement: '', kind: '', value: '', unit: '', period: '' });

export function formFromCandidate(c: ClaimCandidate): ClaimFormState {
  return {
    statement: c.quote ?? '',
    kind: c.kind ?? '',
    value: c.value === null || c.value === undefined ? '' : String(c.value),
    unit: c.unit ?? '',
    period: c.period ?? '',
  };
}

export function formFromSource(s: ClaimSource): ClaimFormState {
  return {
    statement: s.statement_text,
    kind: s.kind,
    value: s.value === null || s.value === undefined ? '' : String(s.value),
    unit: s.unit ?? '',
    period: s.period ?? '',
  };
}

export const formFromClaim = (c: ProjectClaimView): ClaimFormState => formFromSource(c.source);

export type FormField = keyof ClaimFormState;
export type FormErrors = Partial<Record<FormField, string>>;

export type FormCheck =
  | { ok: true; fields: { statement_text: string; kind: string; value: number | null; unit: string | null; period: string | null } }
  | { ok: false; errors: FormErrors };

const squash = (s: string) => s.split(/\s+/).filter(Boolean).join(' ');

/** Checks the form the way the API will, so a mistake is caught before sending. */
export function validateClaimForm(form: ClaimFormState, kinds: readonly Pick<ClaimKindView, 'kind'>[]): FormCheck {
  const errors: FormErrors = {};
  const statement = squash(form.statement);
  if (statement.length < STATEMENT_MIN) errors.statement = `Write the claim in at least ${STATEMENT_MIN} characters.`;
  else if (statement.length > STATEMENT_MAX) errors.statement = `The claim can be at most ${STATEMENT_MAX} characters (it is ${statement.length}).`;

  if (!form.kind) errors.kind = 'Choose what kind of claim this is.';
  else if (!kinds.some((k) => k.kind === form.kind)) errors.kind = 'That claim type is not one of the available types.';

  let value: number | null = null;
  const rawValue = form.value.trim();
  if (rawValue !== '') {
    const n = Number(rawValue.replace(/,/g, ''));
    if (!Number.isFinite(n)) errors.value = 'The number must be digits only, for example 1200 or 84.5. Leave it empty if the claim has no number.';
    else value = n;
  }

  const unit = squash(form.unit);
  if (unit.length > UNIT_MAX) errors.unit = `The unit can be at most ${UNIT_MAX} characters.`;
  const period = squash(form.period);
  if (period.length > PERIOD_MAX) errors.period = `The period can be at most ${PERIOD_MAX} characters.`;

  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return { ok: true, fields: { statement_text: statement, kind: form.kind, value, unit: unit || null, period: period || null } };
}

/** Help text beside the form fields so people know what each one does. */
export const FORM_HELP = {
  statement: 'What is being claimed, in plain words. Fix a misread phrase here; the document itself is never changed.',
  value: 'The number the claim states, if any.',
  unit: 'For example ha, %, tCO2e.',
  period: 'For example 2019-2023.',
} as const;

/* ---- showing what changed ---- */

const fmtVal = (v: number | null | undefined, unit: string | null | undefined) =>
  v === null || v === undefined ? '' : `${v.toLocaleString('en-US', { maximumFractionDigits: 6 })}${unit ? ` ${unit}` : ''}`;

/** What the document said as a figure: the number the reader found, its unit and period. */
export function originalSummary(s: ClaimSource): string {
  const fig = fmtVal(s.original_value, s.original_unit);
  return fig ? `${fig}${s.original_period ? ` (${s.original_period})` : ''}` : s.original_period ?? '';
}

/** What is actually being tested, as a figure. */
export function testedSummary(s: ClaimSource): string {
  const fig = fmtVal(s.value, s.unit);
  return fig ? `${fig}${s.period ? ` (${s.period})` : ''}` : s.period ?? '';
}

/** The plain sentence shown when someone corrected the extraction. Null when nothing was changed. */
export function correctionNotice(s: ClaimSource): string | null {
  if (!s.edited) return null;
  const said = originalSummary(s);
  const tested = testedSummary(s);
  const parts: string[] = [];
  if (said !== tested) parts.push(`the document said ${said || 'no figure'}, tested as ${tested || 'no figure'}`);
  if (s.original_kind && s.original_kind !== s.kind) parts.push('the claim type was changed');
  if (squash(s.statement_text) !== squash(s.original_text)) parts.push('the wording was changed');
  return parts.length ? `You corrected this: ${parts.join('; ')}.` : 'You corrected this claim after it was read from the document.';
}

/* ---- API errors ---- */

const CODE_COPY: Record<string, string> = {
  already_promoted: 'This statement is already a claim in this project.',
  source_not_found: 'That statement could not be found in the document.',
  document_not_readable: 'The document could not be read, so the statement cannot be added from it.',
  too_many_claims: 'This project already has the most claims it can hold.',
  invalid_claim: 'Some of the claim details are not valid.',
};

export function apiDetail(body: unknown): { code: string | null; message: string | null; hint: string | null } {
  const d = (body as { detail?: unknown } | null | undefined)?.detail;
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    const { code, message, hint } = d as { code?: unknown; message?: unknown; hint?: unknown };
    return {
      code: typeof code === 'string' ? code : null,
      message: typeof message === 'string' && message ? message : null,
      hint: typeof hint === 'string' && hint ? hint : null,
    };
  }
  return { code: null, message: typeof d === 'string' && d ? d : null, hint: null };
}

/** The API's message plus hint when sent; otherwise wording chosen from the code, then from the status. */
export function claimErrorMessage(status: number, body: unknown): string {
  const { code, message, hint } = apiDetail(body);
  const base = message ?? (code ? CODE_COPY[code] : undefined) ?? null;
  if (base) return hint ? `${base} ${hint}` : base;
  switch (status) {
    case 0:
      return 'The GroundTruth API could not be reached. Nothing was changed.';
    case 401:
      return 'Your session has expired. Sign in again.';
    case 403:
      return 'Your access level does not allow changing claims in this project.';
    case 404:
      return 'The claim, document or project was not found, or you have no access to it.';
    case 409:
      return 'This change conflicts with the current state of the project. Refresh and try again.';
    case 422:
      return 'Some of the claim details are not valid.';
    default:
      return `The server could not complete the request (HTTP ${status}).`;
  }
}

export const EDIT_BLOCKED = 'You can read claims but not change them: your role or this project is read-only for you.';
