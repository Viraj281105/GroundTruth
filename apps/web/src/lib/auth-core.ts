/** Pure auth helpers shared by the shell and the auth pages. No network, so they are unit-tested. */

export type Role = 'user' | 'dev' | 'admin';

/** Rank: user < dev < admin. A higher role can do everything a lower one can. */
const RANK: Record<Role, number> = { user: 0, dev: 1, admin: 2 };

export const ROLE_LABELS: Record<Role, string> = { user: 'User', dev: 'Developer', admin: 'Admin' };

export interface AuthUser {
  id: string;
  email: string;
  role: Role;
  is_active: boolean;
}

export function parseRole(value: unknown): Role | null {
  return value === 'user' || value === 'dev' || value === 'admin' ? value : null;
}

/** True when `role` is at least `minimum`. A missing role (signed out) never passes. */
export function hasRole(role: Role | null | undefined, minimum: Role): boolean {
  return role ? RANK[role] >= RANK[minimum] : false;
}

/** Up to two letters for the avatar: "ada.lovelace@x.org" -> "AL", "bob@x.org" -> "B". */
export function initials(email: string): string {
  const local = (email.split('@')[0] ?? '').trim();
  const parts = local.split(/[._\-+\s]+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : (parts[0] ?? '?').slice(0, 1);
  return letters.toUpperCase();
}

/** Where a signed-in user may go from the account menu, by role. */
export interface MenuLink {
  href: string;
  label: string;
}

export function menuLinksFor(role: Role | null | undefined): MenuLink[] {
  const links: MenuLink[] = [];
  if (role) links.push({ href: '/account', label: 'Account' });
  links.push({ href: '/method', label: 'How it works' });
  if (hasRole(role, 'dev')) links.push({ href: '/status', label: 'System status' });
  if (hasRole(role, 'admin')) links.push({ href: '/admin/users', label: 'Manage users' });
  return links;
}
