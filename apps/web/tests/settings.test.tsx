import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { components } from '../src/lib/generated/schema';
import { validateGrantSlug, assignableRoles, canManageSettings, memberControls, settingsRedirect } from '../src/features/settings/model';
import { MembersTable } from '../src/features/settings/MembersTable';

type Member = components['schemas']['MemberView'];
type Role = Member['role'];
const m = (id: string, role: Role): Member => ({ user_id: id, email: `${id}@x.org`, role, created_at: '2026-01-01T00:00:00Z' });

describe('settings gating', () => {
  it('only owners and admins reach settings; others are redirected to the dashboard', () => {
    expect(canManageSettings('owner')).toBe(true);
    expect(canManageSettings('admin')).toBe(true);
    expect(canManageSettings('member')).toBe(false);
    expect(canManageSettings('viewer')).toBe(false);
    expect(settingsRedirect('demo', 'owner')).toBeNull();
    expect(settingsRedirect('demo', 'member')).toBe('/app/demo/dashboard');
    expect(settingsRedirect('demo', 'viewer')).toBe('/app/demo/dashboard');
  });
  it('member and viewer get no member controls', () => {
    for (const actor of ['member', 'viewer'] as Role[]) {
      for (const target of ['owner', 'admin', 'member', 'viewer'] as Role[]) {
        expect(memberControls(actor, target, false)).toEqual({ canChangeRole: false, canRemove: false });
      }
      expect(assignableRoles(actor)).toEqual([]);
    }
  });
  it('an admin cannot touch owner rows or assign owner', () => {
    expect(memberControls('admin', 'owner', false)).toEqual({ canChangeRole: false, canRemove: false });
    expect(memberControls('admin', 'admin', false).canChangeRole).toBe(true);
    expect(assignableRoles('admin')).toEqual(['admin', 'member', 'viewer']);
  });
  it('an owner can change and remove anyone, including owners, but not remove themselves', () => {
    expect(assignableRoles('owner')).toEqual(['owner', 'admin', 'member', 'viewer']);
    expect(memberControls('owner', 'owner', false)).toEqual({ canChangeRole: true, canRemove: true });
    expect(memberControls('owner', 'viewer', true)).toEqual({ canChangeRole: true, canRemove: false });
  });
});

describe('MembersTable', () => {
  const members = [m('u1', 'owner'), m('u2', 'admin'), m('u3', 'viewer')];
  const html = (role: Role) => renderToStaticMarkup(<MembersTable orgSlug="o" actorRole={role} actorUserId="u9" initialMembers={members} />);
  it('renders no controls for a viewer', () => {
    const h = html('viewer');
    expect(h).not.toMatch(/<select/);
    expect(h).not.toMatch(/Remove/);
    expect(h).not.toMatch(/Add member/);
  });
  it('an admin sees controls on non-owner rows only', () => {
    const h = html('admin');
    expect((h.match(/Remove/g) ?? []).length).toBeGreaterThan(0);
    const ownerRow = h.split('<tr').find((r) => r.includes('u1@x.org')) ?? '';
    expect(ownerRow).not.toMatch(/<select/);
    expect(ownerRow).not.toMatch(/Remove/);
    expect(h).toMatch(/Add member/);
  });
});

describe('validateGrantSlug', () => {
  it('rejects empty, malformed and the owning org; accepts plain slugs', () => {
    expect(validateGrantSlug('', 'own')).not.toBeNull();
    expect(validateGrantSlug('Bad Slug', 'own')).not.toBeNull();
    expect(validateGrantSlug('-x', 'own')).not.toBeNull();
    expect(validateGrantSlug('own', 'own')).toMatch(/already belongs/);
    expect(validateGrantSlug('demo-funder-2', 'own')).toBeNull();
  });
});
