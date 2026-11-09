import type { Schemas } from '../../lib/api-client';

/** Org type and member role come from the generated API schema, never hand-written. */
export type OrgType = Schemas['OrgView']['type'];
export type MemberRole = Schemas['OrgView']['role'];

export type NavIcon = 'dashboard' | 'projects' | 'new' | 'portfolio' | 'members' | 'sharing' | 'audit';

export interface NavItem {
  id: string;
  label: string;
  /** Path below `/app/<org>/`. */
  segment: string;
  icon: NavIcon;
  /** True while the page is not built yet: shown with a "Soon" tag and not linked. */
  planned: boolean;
}

export interface NavGroup {
  id: 'workspace' | 'organization';
  label: string;
  items: NavItem[];
}

/** Pages that exist today. Everything else in the navigation is listed but marked as planned. */
const IMPLEMENTED = new Set([
  'dashboard',
  'projects',
  'projects/new',
  'portfolio',
  'settings/members',
  'settings/sharing',
  'settings/audit',
]);

const item = (id: string, label: string, segment: string, icon: NavIcon): NavItem => ({
  id,
  label,
  segment,
  icon,
  planned: !IMPLEMENTED.has(segment),
});

export const PERSPECTIVE_LABELS: Record<OrgType, string> = {
  ngo: 'NGO perspective',
  funder: 'Funder perspective',
  auditor: 'Auditor perspective',
  government: 'Government perspective',
  reference: 'Reference perspective',
};

export const MEMBER_ROLE_LABELS: Record<MemberRole, string> = {
  owner: 'Owner',
  admin: 'Admin',
  member: 'Member',
  viewer: 'Viewer',
};

/**
 * Navigation for one organization. The org type decides the perspective (Portfolio is for funders
 * and governments only); the member role decides what may be changed (settings need owner/admin,
 * creating a project needs write access). The reference org is read-only for everyone.
 * Authorization itself is always enforced by the API; this only avoids offering dead ends.
 */
export function navigationFor(orgType: OrgType, role: MemberRole): NavGroup[] {
  const workspace: NavItem[] = [item('dashboard', 'Dashboard', 'dashboard', 'dashboard'), item('projects', 'Projects', 'projects', 'projects')];
  if (orgType === 'funder' || orgType === 'government') workspace.push(item('portfolio', 'Portfolio', 'portfolio', 'portfolio'));
  if (orgType !== 'reference' && role !== 'viewer') workspace.push(item('new-project', 'New project', 'projects/new', 'new'));
  const groups: NavGroup[] = [{ id: 'workspace', label: 'Workspace', items: workspace }];
  if (role === 'owner' || role === 'admin') {
    groups.push({
      id: 'organization',
      label: 'Organization',
      items: [
        item('members', 'Members', 'settings/members', 'members'),
        item('sharing', 'Sharing', 'settings/sharing', 'sharing'),
        item('audit', 'Audit log', 'settings/audit', 'audit'),
      ],
    });
  }
  return groups;
}

export const navHref = (orgSlug: string, it: NavItem): string => `/app/${orgSlug}/${it.segment}`;

/** Active when the path is the item's route or below it (`projects/new` wins over `projects`). */
export function isNavActive(pathname: string, orgSlug: string, it: NavItem, all: NavItem[]): boolean {
  const href = navHref(orgSlug, it);
  const on = (h: string) => pathname === h || pathname.startsWith(`${h}/`);
  if (!on(href)) return false;
  return !all.some((o) => o !== it && o.segment.startsWith(`${it.segment}/`) && on(navHref(orgSlug, o)));
}

/** The four destinations of the mobile bottom bar; everything else is in the sheet. */
export function mobileTabs(groups: NavGroup[]): NavItem[] {
  return groups.flatMap((g) => g.items).filter((i) => i.id === 'dashboard' || i.id === 'projects' || i.id === 'portfolio');
}
