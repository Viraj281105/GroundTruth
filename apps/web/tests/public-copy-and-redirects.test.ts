import { describe, expect, it } from 'vitest';
import { buildFacts, faqs, notYet, works } from '../src/features/home/data';
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
    expect(notYet.join(' ')).toMatch(/stakeholder summary reports/i);
    // No causal analysis of a real project exists; that part of the old statement is still true.
    expect(homeCopy.status).toContain('no real project has been analysed causally');
  });

  it('describes satellite ingestion as it is: available for your own project, measured, not validated', () => {
    // The observation-ingestion workflow exists (and runs in the Docker stack), so the site must not
    // list it as missing or say that no real satellite data is used. It must not overstate it either.
    expect(notYet.join(' ')).not.toMatch(/live satellite ingestion/i);
    expect(notYet.join(' ')).toMatch(/no attribution to the project yet/i);
    expect(notYet.join(' ')).toMatch(/field validation/i);
    expect(works.join(' ')).toMatch(/Sentinel-2 observation requests.*not field-validated/i);
    expect(homeCopy.status).toMatch(/real Sentinel-2 observations/);
    expect(homeCopy.status).toMatch(/not field-validated/);
    const faq = faqs.find((f) => f.q.startsWith('Does it use real satellite data'))!.a;
    expect(faq).toMatch(/^For a project you create, yes/);
    expect(faq).toMatch(/not validated against field data/);
    expect(faq).toMatch(/not carbon, survival or a project effect/);
    expect(faq).toMatch(/Simulated data/);
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
