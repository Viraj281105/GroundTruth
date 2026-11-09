import type { Schemas } from '../../lib/api-client';
import type { DataMode } from '../../components/ds/DataModeBanner';
import type { MemberRole, OrgType } from '../../components/shell/navigation';

export type ProjectView = Schemas['ProjectView'];
export type AccessLevel = ProjectView['access_level'];

export interface WorkspaceTab {
  segment: 'overview' | 'observation' | 'climate' | 'evidence' | 'verification' | 'reports' | 'activity';
  label: string;
}

export const WORKSPACE_TABS: readonly WorkspaceTab[] = [
  { segment: 'overview', label: 'Overview' },
  { segment: 'observation', label: 'Earth Observation' },
  { segment: 'climate', label: 'Climate' },
  { segment: 'evidence', label: 'Evidence' },
  { segment: 'verification', label: 'Verification' },
  { segment: 'reports', label: 'Reports' },
  { segment: 'activity', label: 'Activity' },
];

/** Every level sees every tab; what differs is the content inside (the API redacts, the UI never invents). */
export function tabsFor(_level: AccessLevel): readonly WorkspaceTab[] {
  return WORKSPACE_TABS;
}

/** Causal diagnostics (weights, placebo, leave-one-out, spec curve) exist for owner and audit only. */
export const diagnosticsAllowed = (level: AccessLevel): boolean => level === 'owner' || level === 'audit';
/** Diagnostics render only when the verification payload carries a bundle AND the level allows them. */
export const diagnosticsVisible = <B,>(bundle: B | null | undefined, level: AccessLevel): bundle is B => Boolean(bundle) && diagnosticsAllowed(level);
export const dossierVisible = (level: AccessLevel): boolean => level === 'owner' || level === 'audit';
export const legacyReportsAvailable = (caseId: string | null | undefined): boolean => Boolean(caseId);

/** A project with no uploaded boundary is a library case: it carries no boundary and no data of its own. */
export const isLibraryCase = (p: Pick<ProjectView, 'boundary_sha256'>): boolean => p.boundary_sha256 === null;

/** Library cases never raise the synthetic banner; they are not synthetic output, they are empty. */
export function projectDataMode(p: Pick<ProjectView, 'boundary_sha256' | 'data_mode'>): DataMode {
  return isLibraryCase(p) ? 'observed' : p.data_mode;
}

export function dataModeLabel(p: Pick<ProjectView, 'boundary_sha256' | 'data_mode'>): string {
  if (isLibraryCase(p)) return 'library case — no boundary or data';
  // "Observed" means a real project rather than a simulation. It does not mean satellite data has been
  // ingested (the stepper and Evidence tab say what data exists), so the label says "real project".
  return p.data_mode === 'simulated' ? 'Simulated data' : 'Real project (not simulated)';
}

/** Uploading and deleting documents needs owner-level access to the project AND an org role that may edit (not a viewer). */
export const canEditProject = (level: AccessLevel, role: MemberRole | null | undefined): boolean => level === 'owner' && (role === 'owner' || role === 'admin' || role === 'member');

export function editBlockedReason(level: AccessLevel, role: MemberRole | null | undefined): string | null {
  if (canEditProject(level, role)) return null;
  if (level !== 'owner') return 'This project belongs to another organization and was shared with you, so you can read its documents but not change them.';
  return 'Your role in this organization is read-only, so you cannot upload or delete documents. Ask an organization owner or admin to change your role.';
}

export const canCreateProject = (orgType: OrgType, role: MemberRole): boolean => orgType !== 'reference' && role !== 'viewer';

/** Portfolio is a funder/government view; everyone else goes back to the dashboard. */
export function portfolioRedirect(orgSlug: string, orgType: OrgType): string | null {
  return orgType === 'funder' || orgType === 'government' ? null : `/app/${orgSlug}/dashboard`;
}

/** A readable message for an API failure. Server detail (422, 409) is shown as sent; status is the fallback. */
export function apiErrorMessage(status: number, detail?: string | null): string {
  if (detail && (status === 422 || status === 409 || status === 400)) return detail;
  switch (status) {
    case 0:
      return 'The GroundTruth API could not be reached. Nothing was changed.';
    case 401:
      return 'Your session has expired. Sign in again.';
    case 403:
      return 'Your role does not allow this action.';
    case 413:
      return 'The boundary file is larger than 5 MB.';
    case 404:
      return 'Not found, or you have no access to it.';
    case 422:
    case 400:
      return 'The server rejected the submitted data.';
    case 409:
      return 'This conflicts with the current state.';
    default:
      return `The server could not complete the request (HTTP ${status}).`;
  }
}

/** Pulls the `detail` string out of an error body, if it has one. */
export function detailOf(body: unknown): string | null {
  const d = (body as { detail?: unknown } | null | undefined)?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    const msgs = d.map((x) => (x && typeof x === 'object' && 'msg' in x ? String((x as { msg: unknown }).msg) : null)).filter(Boolean);
    return msgs.length ? msgs.join('; ') : null;
  }
  return null;
}
