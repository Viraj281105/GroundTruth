import { describe, expect, it } from 'vitest';
import { errorMessage, isValidEmail, passwordChecks, passwordProblem, safeNextPath, strengthScore } from './validate';

describe('isValidEmail', () => {
  it('accepts normal addresses and rejects junk', () => {
    expect(isValidEmail('ada@example.org')).toBe(true);
    expect(isValidEmail(' ada.l+x@sub.example.org ')).toBe(true);
    for (const bad of ['', 'ada', 'ada@', '@x.org', 'a b@x.org', 'ada@x', 'a@@x.org']) expect(isValidEmail(bad)).toBe(false);
  });
});

describe('password policy', () => {
  it('mirrors the server rules', () => {
    expect(passwordProblem('short', '')).toMatch(/at least 10/);
    expect(passwordProblem('x'.repeat(129), '')).toMatch(/at most 128/);
    expect(passwordProblem('Ada@Example.org', 'ada@example.org')).toMatch(/email/);
    expect(passwordProblem('GroundTruth123', '')).toMatch(/common/);
    expect(passwordProblem('Password123', '')).toMatch(/common/);
    expect(passwordProblem('aaaaaaaaaaaa', '')).toMatch(/common/);
    expect(passwordProblem('correct horse battery', 'a@b.co')).toBeNull();
  });
  it('builds a live checklist', () => {
    const c = passwordChecks('short', 'a@b.co');
    expect(c.find((x) => x.id === 'length')?.ok).toBe(false);
    expect(passwordChecks('correct horse battery').every((x) => x.ok)).toBe(true);
  });
});

describe('strengthScore', () => {
  it('is 0 for rejected passwords and rises with length and variety', () => {
    expect(strengthScore('').score).toBe(0);
    expect(strengthScore('password123').score).toBe(0);
    expect(strengthScore('aaaaaaaaaaaa').score).toBe(0);
    const fair = strengthScore('abcdefghijk1');
    const strong = strengthScore('Tr0ub4dor&3-horse-staple');
    expect(strong.score).toBe(4);
    expect(strong.label).toBe('Strong');
    expect(fair.score).toBeLessThan(strong.score);
    expect(fair.score).toBeGreaterThan(0);
  });
});

describe('safeNextPath', () => {
  it('keeps same-origin relative paths', () => {
    expect(safeNextPath('/cases/kariba-redd/run')).toBe('/cases/kariba-redd/run');
    expect(safeNextPath('/claims?x=1')).toBe('/claims?x=1');
  });
  it('rejects open-redirect and loop attempts', () => {
    for (const bad of ['//evil.com', '/\\evil.com', 'https://evil.com', 'javascript:alert(1)', '/login', '/login?next=/', '/register', 'evil', '', '/%2F%2Fevil.com', '/a\\b', '/\nfoo']) {
      expect(safeNextPath(bad), bad).toBe('/');
    }
    expect(safeNextPath(null)).toBe('/');
    expect(safeNextPath(undefined, '/home')).toBe('/home');
  });
});

describe('errorMessage', () => {
  it('maps every server code to plain language', () => {
    const codes = ['invalid_credentials', 'email_taken', 'weak_password', 'too_many_attempts', 'unauthenticated', 'forbidden', 'csrf_origin_rejected', 'registration_closed', 'store_not_configured', 'last_admin', 'network'];
    const seen = new Set(codes.map((c) => errorMessage(c)));
    expect(seen.size).toBe(codes.length);
    for (const m of seen) expect(m).not.toMatch(/_/);
  });
  it('uses Retry-After when given', () => {
    expect(errorMessage('too_many_attempts', 900)).toMatch(/15 minutes/);
    expect(errorMessage('too_many_attempts', 30)).toMatch(/30 seconds/);
    expect(errorMessage('too_many_attempts')).toMatch(/few minutes/);
  });
  it('has a safe fallback', () => {
    expect(errorMessage('weird')).toMatch(/went wrong/);
    expect(errorMessage(null)).toMatch(/went wrong/);
  });
});
