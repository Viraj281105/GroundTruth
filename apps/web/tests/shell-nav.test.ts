import { describe, expect, it } from 'vitest';
import { isNavActive, mobileTabs, navHref, navigationFor, type MemberRole, type OrgType } from '../src/components/shell/navigation';

const TYPES: OrgType[] = ['ngo', 'funder', 'auditor', 'government', 'reference'];
const ROLES: MemberRole[] = ['owner', 'admin', 'member', 'viewer'];
const ids = (t: OrgType, r: MemberRole) => navigationFor(t, r).flatMap((g) => g.items.map((i) => i.id));

describe('navigationFor', () => {
  it('shows Portfolio only to funders and governments', () => {
    for (const t of TYPES) for (const r of ROLES) expect(ids(t, r).includes('portfolio')).toBe(t === 'funder' || t === 'government');
  });

  it('shows settings (members, sharing, audit) only to owners and admins', () => {
    for (const t of TYPES) {
      for (const r of ROLES) {
        const has = ['members', 'sharing', 'audit'].map((id) => ids(t, r).includes(id));
        const allowed = r === 'owner' || r === 'admin';
        expect(has, `${t}/${r}`).toEqual([allowed, allowed, allowed]);
      }
    }
  });

  it('keeps the reference org read-only: no New project for anyone', () => {
    for (const r of ROLES) expect(ids('reference', r)).not.toContain('new-project');
  });

  it('offers New project to non-viewer members of writable org types only', () => {
    expect(ids('ngo', 'member')).toContain('new-project');
    expect(ids('ngo', 'owner')).toContain('new-project');
    expect(ids('ngo', 'viewer')).not.toContain('new-project');
  });

  it('always starts with Dashboard and Projects', () => {
    for (const t of TYPES) for (const r of ROLES) expect(ids(t, r).slice(0, 2)).toEqual(['dashboard', 'projects']);
  });

  it('links every item that has a page (all current items are built)', () => {
    for (const t of TYPES) for (const r of ROLES) {
      const items = navigationFor(t, r).flatMap((g) => g.items);
      expect(items.filter((i) => i.planned).map((i) => i.id), `${t}/${r}`).toEqual([]);
    }
  });

  it('points each item at its route', () => {
    const items = navigationFor('funder', 'owner').flatMap((g) => g.items);
    expect(items.map((i) => i.segment)).toEqual(['dashboard', 'projects', 'portfolio', 'projects/new', 'settings/members', 'settings/sharing', 'settings/audit']);
  });
});

describe('navigation helpers', () => {
  const items = navigationFor('ngo', 'owner').flatMap((g) => g.items);
  const get = (id: string) => items.find((i) => i.id === id)!;

  it('builds org-scoped hrefs', () => {
    expect(navHref('demo-ngo', get('dashboard'))).toBe('/app/demo-ngo/dashboard');
    expect(navHref('demo-ngo', get('members'))).toBe('/app/demo-ngo/settings/members');
  });

  it('marks the most specific item active', () => {
    expect(isNavActive('/app/o/projects/new', 'o', get('new-project'), items)).toBe(true);
    expect(isNavActive('/app/o/projects/new', 'o', get('projects'), items)).toBe(false);
    expect(isNavActive('/app/o/projects/kariba/overview', 'o', get('projects'), items)).toBe(true);
    expect(isNavActive('/app/other/dashboard', 'o', get('dashboard'), items)).toBe(false);
  });

  it('puts at most dashboard, projects and portfolio in the mobile tab bar', () => {
    expect(mobileTabs(navigationFor('funder', 'owner')).map((i) => i.id)).toEqual(['dashboard', 'projects', 'portfolio']);
    expect(mobileTabs(navigationFor('ngo', 'viewer')).map((i) => i.id)).toEqual(['dashboard', 'projects']);
  });
});
