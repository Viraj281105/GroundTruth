import { describe, expect, it } from 'vitest';
import { buildFacts, notYet, works } from '../src/features/home/data';
import { homeCopy } from '../src/features/home/copy';
import { glossary } from '../src/lib/glossary';
import nextConfig from '../next.config.mjs';

describe('landing copy tells the truth about what exists', () => {
  it('lists sign-in, workspaces, boundary upload, dossier export and claim screening as working', () => {
    const text = works.join(' ').toLowerCase();
    for (const term of ['sign-in', 'organisation workspaces', 'boundary upload', 'dossier', 'ledger', 'claim-text screening']) expect(text).toContain(term);
  });

  it('no longer says export and sign-in are planned, and names what is genuinely missing', () => {
    expect(notYet.join(' ')).not.toMatch(/sign-in|export/i);
    expect(notYet.join(' ')).toMatch(/live satellite ingestion for newly created projects/i);
    expect(notYet.join(' ')).toMatch(/stakeholder summary reports/i);
    expect(homeCopy.status).toContain('no real project has been analysed');
  });

  it('never reports benchmark cases as real projects', () => {
    for (const n of [null, 0, 3, 12]) expect(buildFacts(n).find((f) => f.id === 'real')?.value).toBe(0);
  });

  it('explains dashboard jargon in the shared glossary', () => {
    for (const id of ['attribution-readiness', 'spi', 'att', 'ndvi', 'donor-pool']) expect(glossary(id)?.plain.length).toBeGreaterThan(20);
  });
});

describe('/sign-in', () => {
  it('redirects to /login (Next keeps the query string, so ?next survives)', async () => {
    const rules = await nextConfig.redirects!();
    expect(rules).toContainEqual({ source: '/sign-in', destination: '/login', permanent: false });
  });
});
