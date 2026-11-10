import { describe, expect, it } from 'vitest';
import { formatIndexValue, splitGuardrail } from '../../src/components/panels/format';
import { TOUR_STEPS } from '../../src/lib/tour-core';

/** Display defects found in the user audit. */
describe('formatIndexValue', () => {
  it('shows an index to four decimals instead of sixteen digits of arithmetic', () => {
    expect(formatIndexValue(0.28870252745691166)).toBe('0.2887');
    expect(formatIndexValue(-0.14124152403027868)).toBe('-0.1412');
    expect(formatIndexValue(0.3)).toBe('0.3000');
  });

  it('never prints NaN or Infinity', () => {
    expect(formatIndexValue(Number.NaN)).toBe('-');
    expect(formatIndexValue(Number.POSITIVE_INFINITY)).toBe('-');
  });
});

describe('splitGuardrail', () => {
  it('separates the engine identifier from the sentence a reader needs', () => {
    expect(splitGuardrail('assert_not_index_to_carbon: Optical indices (NDVI/EVI) cannot be converted to tCO2e.')).toEqual({
      id: 'assert_not_index_to_carbon',
      text: 'Optical indices (NDVI/EVI) cannot be converted to tCO2e.',
    });
  });

  it('leaves ordinary sentences, including ones with a colon, untouched', () => {
    expect(splitGuardrail('Note: greening is not attribution.')).toEqual({ id: null, text: 'Note: greening is not attribution.' });
    expect(splitGuardrail('No identifier here')).toEqual({ id: null, text: 'No identifier here' });
  });
});

describe('welcome tour copy', () => {
  const text = TOUR_STEPS.map((s) => `${s.title} ${s.body}`).join(' ');

  it('does not promise a counterfactual estimate, which a user project cannot get', () => {
    expect(text).not.toMatch(/twin|what a restoration or carbon project actually achieved/i);
  });

  it('does not say that no real project has been analysed', () => {
    expect(text).not.toMatch(/no real project has been analysed/i);
    expect(text).toMatch(/real Sentinel-2 observations/);
  });

  it('still says simulated data is labelled and that gaps are never filled in', () => {
    expect(text).toMatch(/Simulated data/);
    expect(text).toMatch(/never filled in/);
  });
});
