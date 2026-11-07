import { describe, expect, it } from 'vitest';
import { segmentText } from './highlight';

describe('segmentText', () => {
  it('returns the whole text when there are no spans', () => {
    expect(segmentText('abc', [])).toEqual([{ text: 'abc', claim: null }]);
  });
  it('splits around spans and round-trips', () => {
    const text = 'area 12 ha, baseline 5 t';
    const segs = segmentText(text, [{ start: 5, end: 10 }, { start: 21, end: 24 }]);
    expect(segs.map((s) => s.text).join('')).toBe(text);
    expect(segs.filter((s) => s.claim !== null).map((s) => s.claim)).toEqual([0, 1]);
    expect(segs[1].text).toBe('12 ha');
  });
  it('keeps original indexes when spans are unsorted', () => {
    const segs = segmentText('abcdef', [{ start: 4, end: 6 }, { start: 0, end: 2 }]);
    expect(segs.filter((s) => s.claim !== null).map((s) => [s.text, s.claim])).toEqual([['ab', 1], ['ef', 0]]);
  });
  it('skips overlapping and invalid spans', () => {
    const segs = segmentText('abcdef', [{ start: 0, end: 4 }, { start: 2, end: 5 }, { start: -1, end: 2 }, { start: 3, end: 99 }, { start: 3, end: 3 }]);
    expect(segs.map((s) => s.text).join('')).toBe('abcdef');
    expect(segs.filter((s) => s.claim !== null)).toHaveLength(1);
  });
});
