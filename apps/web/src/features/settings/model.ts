import type { Schemas } from '../../lib/api-client';

export type Role = Schemas['MemberView']['role'];
export const ALL_ROLES: readonly Role[] = ['owner', 'admin', 'member', 'viewer'];

export const canManageSettings = (role: Role): boolean => role === 'owner' || role === 'admin';

/** Where a caller without settings access goes instead (null = stay). */
export const settingsRedirect = (orgSlug: string, role: Role): string | null => (canManageSettings(role) ? null : `/app/${orgSlug}/dashboard`);

/** Roles the actor may hand out: owners any, admins everything but owner. The API enforces the same. */
export function assignableRoles(actor: Role): Role[] {
  if (actor === 'owner') return [...ALL_ROLES];
  if (actor === 'admin') return ALL_ROLES.filter((r) => r !== 'owner');
  return [];
}

export interface MemberControls {
  canChangeRole: boolean;
  canRemove: boolean;
}

/** Which controls a row offers. Admins cannot touch owner rows; nobody removes themselves here. */
export function memberControls(actor: Role, target: Role, isSelf: boolean): MemberControls {
  if (!canManageSettings(actor)) return { canChangeRole: false, canRemove: false };
  if (actor === 'admin' && target === 'owner') return { canChangeRole: false, canRemove: false };
  return { canChangeRole: true, canRemove: !isSelf };
}

/** Client-side check of a grantee slug; the API stays authoritative. */
export function validateGrantSlug(slug: string, ownerSlug: string): string | null {
  if (!slug) return 'Enter the slug of the organization to share with.';
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug)) return 'An organization slug uses lowercase letters, digits and hyphens only.';
  if (slug === ownerSlug.toLowerCase()) return 'This project already belongs to that organization.';
  return null;
}
