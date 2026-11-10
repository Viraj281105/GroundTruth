import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { Schemas } from '../src/lib/api-client';
import { legacyCaseDestination } from '../src/lib/legacy-case-redirect';

type Me = Schemas['MeResponse'];
type Org = Schemas['OrgView'];

const org = (slug: string): Org => ({ slug, name: slug }) as Org;
const me = (active: Org | null, orgs: Org[]): Me => ({ user: { id: 'u1', email: 'u@example.test' }, organizations: orgs, active_organization: active }) as unknown as Me;

/**
 * Found in the user audit: `/cases/<id>` redirected every visitor to `/app/reference/projects/<id>`.
 * Only members of the Reference organization can open that, so a Demo Government user who followed
 * a case link to Kariba got "not found" although the project is shared with their organization.
 */
describe('legacyCaseDestination', () => {
  const gov = org('demo-government');

  it('opens the project under the active organization of the visitor', () => {
    expect(legacyCaseDestination(me(gov, [gov]), 'kariba-redd')).toBe('/app/demo-government/projects/kariba-redd/overview');
  });

  it('falls back to the first organization when none is active', () => {
    expect(legacyCaseDestination(me(null, [org('demo-ngo'), gov]), 'kariba-redd')).toBe('/app/demo-ngo/projects/kariba-redd/overview');
  });

  it('maps old sub-pages to tabs that exist (the old /report page is the Reports tab)', () => {
    const dest = (page: string) => legacyCaseDestination(me(gov, [gov]), 'kariba-redd', page);
    expect(dest('report')).toBe('/app/demo-government/projects/kariba-redd/reports');
    expect(dest('evidence')).toBe('/app/demo-government/projects/kariba-redd/evidence');
    expect(dest('method')).toBe('/app/demo-government/projects/kariba-redd/verification');
    expect(dest('robustness')).toBe('/app/demo-government/projects/kariba-redd/verification');
    expect(dest('run')).toBe('/app/demo-government/projects/kariba-redd/observation');
    expect(dest('something-else')).toBe('/app/demo-government/projects/kariba-redd/overview');
  });

  it('sends a signed-out visitor to sign in and a member of nothing to the no-organization page', () => {
    expect(legacyCaseDestination(null, 'kariba-redd')).toBe('/login?next=%2Fapp');
    expect(legacyCaseDestination(me(null, []), 'kariba-redd')).toBe('/app/no-organization');
  });

  it('escapes the id, so a crafted link cannot leave the projects path', () => {
    expect(legacyCaseDestination(me(gov, [gov]), '../settings')).toBe('/app/demo-government/projects/..%2Fsettings/overview');
  });

  it('next.config no longer hard-codes the Reference organization for case links', () => {
    const config = readFileSync(new URL('../next.config.mjs', import.meta.url), 'utf8');
    expect(config).not.toContain('/app/reference/projects');
    expect(config).toContain("destination: '/open-case/:id'");
  });
});
