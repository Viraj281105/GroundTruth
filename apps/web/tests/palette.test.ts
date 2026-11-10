import { describe, expect, it } from 'vitest';
import { resolveCommands, parseCompareIntent, type PaletteContext } from '../src/lib/palette-core';
import { addRecent, caseIdFromPath, parseRecent, MAX_RECENT } from '../src/lib/recent-core';

const ctx: PaletteContext = {
  cases: [
    { id: 'kariba-redd', name: 'Kariba REDD+ Project' },
    { id: 'mikoko-pamoja', name: 'Mikoko Pamoja' },
    { id: 'southern-cardamom-redd', name: 'Southern Cardamom REDD+ Project' },
  ],
  recent: [],
};

describe('parseCompareIntent', () => {
  it('turns "compare kariba and mikoko" into a compare URL', () => {
    expect(parseCompareIntent('compare kariba and mikoko', ctx.cases)).toBe('/compare?a=kariba-redd&b=mikoko-pamoja');
  });

  it('understands "vs" and "with"', () => {
    expect(parseCompareIntent('kariba vs cardamom', ctx.cases)).toBe('/compare?a=kariba-redd&b=southern-cardamom-redd');
    expect(parseCompareIntent('compare mikoko with kariba', ctx.cases)).toBe('/compare?a=mikoko-pamoja&b=kariba-redd');
  });

  it('returns null when it cannot resolve two distinct cases', () => {
    expect(parseCompareIntent('compare kariba and kariba', ctx.cases)).toBeNull();
    expect(parseCompareIntent('compare kariba and nothing', ctx.cases)).toBeNull();
    expect(parseCompareIntent('hello', ctx.cases)).toBeNull();
  });
});

describe('resolveCommands', () => {
  it('with an empty query lists navigation first', () => {
    const items = resolveCommands('', ctx);
    expect(items[0].group).toBe('Go to');
    expect(items.some((i) => i.href === '/cases')).toBe(true);
  });

  it('finds a case by partial name', () => {
    const items = resolveCommands('mikoko', ctx);
    expect(items[0].href).toBe('/cases/mikoko-pamoja');
  });

  it('puts a natural-language compare first', () => {
    const items = resolveCommands('compare kariba and mikoko', ctx);
    expect(items[0].href).toBe('/compare?a=kariba-redd&b=mikoko-pamoja');
  });

  it('offers theme and lens actions', () => {
    const items = resolveCommands('dark', ctx);
    expect(items.some((i) => i.action === 'theme:dark')).toBe(true);
    expect(resolveCommands('auditor', ctx).some((i) => i.action === 'lens:auditor')).toBe(true);
  });

  it('returns nothing for gibberish', () => {
    expect(resolveCommands('zzzzqqq', ctx)).toEqual([]);
  });

  it('lists recently viewed cases when the query is empty', () => {
    const items = resolveCommands('', { ...ctx, recent: ['mikoko-pamoja'] });
    expect(items.some((i) => i.group === 'Recent' && i.href === '/cases/mikoko-pamoja')).toBe(true);
  });
});

describe('recently viewed', () => {
  it('puts the newest first without duplicates and caps the length', () => {
    let list: string[] = [];
    for (const id of ['a', 'b', 'c', 'a']) list = addRecent(list, id);
    expect(list).toEqual(['a', 'c', 'b']);
    for (let i = 0; i < 20; i += 1) list = addRecent(list, `x${i}`);
    expect(list.length).toBe(MAX_RECENT);
  });

  it('parses stored JSON defensively', () => {
    expect(parseRecent('["a","b"]')).toEqual(['a', 'b']);
    expect(parseRecent('not json')).toEqual([]);
    expect(parseRecent('{"a":1}')).toEqual([]);
    expect(parseRecent(null)).toEqual([]);
  });
});

describe('inside an organization (user audit: the palette search was dead and case links ended in 404)', () => {
  const orgCtx: PaletteContext = { ...ctx, org: 'demo-government' };

  it('opens a project under the organization that is being viewed, never under a fixed one', () => {
    const items = resolveCommands('kariba', orgCtx);
    expect(items[0]).toMatchObject({ group: 'Projects', hint: 'Open project', href: '/app/demo-government/projects/kariba-redd/overview' });
    expect(items.every((i) => !i.href?.startsWith('/cases'))).toBe(true);
    expect(items.every((i) => !i.href?.includes('/app/reference/'))).toBe(true);
  });

  it('offers only destinations that exist inside the organization', () => {
    const hrefs = resolveCommands('', orgCtx).map((i) => i.href).filter(Boolean);
    expect(hrefs).toContain('/app/demo-government/dashboard');
    expect(hrefs).toContain('/app/demo-government/evidence-library');
    expect(hrefs).toContain('/app/demo-government/reports');
    for (const legacy of ['/cases', '/compare', '/claims', '/status']) expect(hrefs).not.toContain(legacy);
  });

  it('lists the organization projects before anything is typed', () => {
    const items = resolveCommands('', orgCtx);
    expect(items.filter((i) => i.group === 'Projects').map((i) => i.label)).toEqual(ctx.cases.map((c) => c.name));
  });

  it('does not suggest the unscoped compare page', () => {
    expect(resolveCommands('compare kariba and mikoko', orgCtx).some((i) => i.href?.startsWith('/compare'))).toBe(false);
  });

  it('recent projects open inside the organization', () => {
    const items = resolveCommands('', { ...orgCtx, recent: ['mikoko-pamoja'] });
    expect(items.find((i) => i.group === 'Recent')?.href).toBe('/app/demo-government/projects/mikoko-pamoja/overview');
  });
});

describe('caseIdFromPath', () => {
  it('reads the project from legacy and organization paths', () => {
    expect(caseIdFromPath('/cases/kariba-redd/evidence')).toBe('kariba-redd');
    expect(caseIdFromPath('/app/demo-ngo/projects/kariba-redd/reports')).toBe('kariba-redd');
    expect(caseIdFromPath('/app/demo-ngo/projects/kariba-redd')).toBe('kariba-redd');
  });

  it('ignores the creation form and non-project pages', () => {
    expect(caseIdFromPath('/app/demo-ngo/projects/new')).toBeNull();
    expect(caseIdFromPath('/app/demo-ngo/projects')).toBeNull();
    expect(caseIdFromPath('/app/demo-ngo/reports')).toBeNull();
  });
});
