import { afterEach, describe, expect, it, vi } from 'vitest';
import { goToNext } from '../src/features/auth/AuthForms';
import { safeAppNextPath } from '../src/features/auth/validate';

describe('post-login navigation', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('leaves with a full navigation to a same-origin /app path', () => {
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { assign } });
    goToNext(safeAppNextPath('/app/demo-ngo/dashboard'));
    expect(assign).toHaveBeenCalledWith('/app/demo-ngo/dashboard');
  });

  it('an off-site next becomes /app before navigating', () => {
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { assign } });
    for (const evil of ['//evil.com', 'https://evil.com/app', '/\evil.com']) goToNext(safeAppNextPath(evil));
    expect(assign.mock.calls.map((c) => c[0])).toEqual(['/app', '/app', '/app']);
  });
});
