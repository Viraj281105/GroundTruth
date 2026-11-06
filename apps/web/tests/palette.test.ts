import { describe, expect, it } from 'vitest';
import { resolveCommands, parseCompareIntent, type PaletteContext } from '../src/lib/palette-core';
import { addRecent, parseRecent, MAX_RECENT } from '../src/lib/recent-core';

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
