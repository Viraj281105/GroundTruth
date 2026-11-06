import { describe, expect, it } from 'vitest';
import { buildCompareUrl, compareRows, parseCompareParams, swapIds } from './compare';
import { COMPARE_COPY } from './copy';
import type { CaseDetail } from '../../lib/types';

describe('compare ids', () => {
  it('round-trips through the URL', () => {
    const url = buildCompareUrl({ a: 'kariba-redd', b: 'mikoko-pamoja' });
    expect(url).toBe('/compare?a=kariba-redd&b=mikoko-pamoja');
    expect(parseCompareParams(new URLSearchParams(url.split('?')[1]))).toEqual({ a: 'kariba-redd', b: 'mikoko-pamoja' });
  });
  it('omits empty ids and swaps', () => {
    expect(buildCompareUrl({ a: '', b: '' })).toBe('/compare');
    expect(swapIds({ a: 'x', b: 'y' })).toEqual({ a: 'y', b: 'x' });
  });
});

describe('compareRows', () => {
  it('never invents run metrics', () => {
    const rows = compareRows({ donor_pool_size: 30, area_ha: 1000 } as CaseDetail);
    const by = Object.fromEntries(rows.map((r) => [r.key, r.value]));
    expect(by.donors).toBe('30');
    expect(by.area).toBe('1,000 ha');
    for (const k of ['effect', 'uncertainty', 'fit', 'placebo', 'verdict']) expect(by[k]).toBeNull();
  });
  it('is all null without a case', () => {
    expect(compareRows(null).every((r) => r.value === null)).toBe(true);
  });
  it('copy avoids prohibited wording', () => {
    expect(JSON.stringify(COMPARE_COPY)).not.toMatch(/fraud|scam|illegal|criminal|guilty|definitive|proves? that/i);
  });
});
