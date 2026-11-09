/** Pure model for the "Create an organization" form: types, plain-language descriptions, validation, error text. */

export type NewOrgType = 'ngo' | 'funder' | 'auditor' | 'government';

export const ORG_TYPE_OPTIONS: ReadonlyArray<{ value: NewOrgType; label: string; plain: string }> = [
  { value: 'ngo', label: 'NGO / Project developer', plain: 'You run or manage restoration or carbon projects and want to check and show their results.' },
  { value: 'funder', label: 'Funder / Investor', plain: 'You pay for projects and want to compare them and see which need a closer look.' },
  { value: 'auditor', label: 'Independent auditor', plain: 'You review other people’s claims and need the full evidence record to do it.' },
  { value: 'government', label: 'Government', plain: 'You oversee landscapes and projects in a region and want a map-first overview.' },
];

export const ORG_NAME_MAX = 200;

export interface OrgFormErrors {
  name?: string;
  type?: string;
}

export function validateOrgForm(name: string, type: string): OrgFormErrors {
  const errors: OrgFormErrors = {};
  const trimmed = name.trim();
  if (!trimmed) errors.name = 'Enter a name for your organization.';
  else if (trimmed.length < 2) errors.name = 'The name needs at least 2 characters.';
  else if (trimmed.length > ORG_NAME_MAX) errors.name = `Keep the name under ${ORG_NAME_MAX} characters.`;
  if (!ORG_TYPE_OPTIONS.some((o) => o.value === type)) errors.type = 'Choose the option that best describes your organization.';
  return errors;
}

/** A friendly message for a failed create call, from the API's `detail: {message}` body or its status. */
export function orgErrorMessage(error: unknown, status?: number): string {
  const detail = (error as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === 'string' && message) return message;
  }
  if (status === 401) return 'Your session has ended. Sign in again, then retry.';
  if (status === 409) return 'An organization with that name already exists. Try a more specific name.';
  if (status === 422) return 'Check the name and type, then try again.';
  if (status === 429) return 'Too many attempts. Wait a moment and try again.';
  if (status && status >= 500) return 'The server had a problem creating the organization. Nothing was created; please try again.';
  return 'Could not create the organization. Please try again.';
}
