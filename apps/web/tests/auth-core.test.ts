import { describe, expect, it } from 'vitest';
import { hasRole, initials, menuLinksFor, parseRole } from '../src/lib/auth-core';

describe('roles', () => {
  it('ranks user < dev < admin', () => {
    expect(hasRole('admin', 'dev')).toBe(true);
    expect(hasRole('dev', 'user')).toBe(true);
    expect(hasRole('user', 'dev')).toBe(false);
    expect(hasRole('dev', 'admin')).toBe(false);
    expect(hasRole('admin', 'admin')).toBe(true);
  });

  it('a signed-out visitor passes no role check', () => {
    expect(hasRole(null, 'user')).toBe(false);
    expect(hasRole(undefined, 'user')).toBe(false);
  });

  it('parseRole accepts only the three roles', () => {
    expect(parseRole('dev')).toBe('dev');
    expect(parseRole('analyst')).toBeNull();
    expect(parseRole(42)).toBeNull();
  });
});

describe('initials', () => {
  it('uses two letters for dotted names and one otherwise', () => {
    expect(initials('ada.lovelace@x.org')).toBe('AL');
    expect(initials('bob@x.org')).toBe('B');
    expect(initials('')).toBe('?');
  });
});

describe('account menu links', () => {
  const hrefs = (r: Parameters<typeof menuLinksFor>[0]) => menuLinksFor(r).map((l) => l.href);

  it('signed out: only the public explainer', () => {
    expect(hrefs(null)).toEqual(['/method']);
  });

  it('user: account and explainer, no status and no admin', () => {
    expect(hrefs('user')).toEqual(['/account', '/method']);
  });

  it('dev: adds system status', () => {
    expect(hrefs('dev')).toEqual(['/account', '/method', '/status']);
  });

  it('admin: adds user management too', () => {
    expect(hrefs('admin')).toEqual(['/account', '/method', '/status', '/admin/users']);
  });
});
