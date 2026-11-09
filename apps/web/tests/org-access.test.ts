import { describe, expect, it } from 'vitest';
import type { Schemas } from '../src/lib/api-client';
import { landingPathFor, loginUrlFor, resolveOrgAccess, switchOutcome } from '../src/lib/org-access';

const org = (slug: string, type: Schemas['OrgView']['type'] = 'ngo'): Schemas['OrgView'] => ({ id: slug, slug, name: slug, type, role: 'member' });
const user = { id: 'u', email: 'a@b.org', role: 'user', is_active: true } as Schemas['MeResponse']['user'];
const me = (orgs: Schemas['OrgView'][], active: Schemas['OrgView'] | null): Schemas['MeResponse'] => ({ auth_required: true, registration_open: false, user, organizations: orgs, active_organization: active });

describe('resolveOrgAccess', () => {
  it('signed out when there is no user', () => {
    expect(resolveOrgAccess(null, 'a').kind).toBe('signed-out');
    expect(resolveOrgAccess({ ...me([org('a')], null), user: null }, 'a').kind).toBe('signed-out');
  });
  it('sends a user with no organizations to /app/no-organization', () => {
    expect(resolveOrgAccess(me([], null), 'a').kind).toBe('no-organization');
  });
  it('404s for a slug the user is not a member of', () => {
    expect(resolveOrgAccess(me([org('a')], org('a')), 'b').kind).toBe('not-found');
  });
  it('continues without a switch when the slug is already active', () => {
    expect(resolveOrgAccess(me([org('a'), org('b')], org('a')), 'a')).toMatchObject({ kind: 'ok', needsSwitch: false });
  });
  it('asks for a switch when the slug is a different membership', () => {
    const r = resolveOrgAccess(me([org('a'), org('b')], org('a')), 'b');
    expect(r).toMatchObject({ kind: 'ok', needsSwitch: true });
    expect(r.kind === 'ok' && r.org.slug).toBe('b');
  });
});

describe('landingPathFor', () => {
  it('goes to login, the active dashboard, the first org, or no-organization', () => {
    expect(landingPathFor(null)).toBe('/login?next=%2Fapp');
    expect(landingPathFor(me([org('a'), org('b')], org('b')))).toBe('/app/b/dashboard');
    expect(landingPathFor(me([org('a'), org('b')], null))).toBe('/app/a/dashboard');
    expect(landingPathFor(me([], null))).toBe('/app/no-organization');
  });
});

describe('loginUrlFor', () => {
  it('returns to the requested /app path, else /app', () => {
    expect(loginUrlFor('/app/b/dashboard?x=1')).toBe(`/login?next=${encodeURIComponent('/app/b/dashboard?x=1')}`);
    expect(loginUrlFor(null)).toBe('/login?next=%2Fapp');
    expect(loginUrlFor('//evil.com')).toBe('/login?next=%2Fapp');
    expect(loginUrlFor('/app/../x')).toBe('/login?next=%2Fapp');
  });
});

describe('switchOutcome', () => {
  it('maps POST /orgs/active statuses; 403 and 5xx are errors, never silent success', () => {
    expect(switchOutcome(200)).toBe('ok');
    expect(switchOutcome(401)).toBe('signed-out');
    expect(switchOutcome(404)).toBe('not-found');
    for (const s of [400, 403, 422, 500, 502]) expect(switchOutcome(s), String(s)).toBe('error');
    expect(switchOutcome(null)).toBe('error');
  });
});
