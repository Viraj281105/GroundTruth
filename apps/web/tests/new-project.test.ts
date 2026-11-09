import { describe, expect, it } from 'vitest';
import { MAX_BOUNDARY_BYTES, validateBoundaryFile } from '../src/features/projects/validate';

const file = (name: string, size: number) => {
  const f = new File(['x'], name, { type: 'application/octet-stream' });
  Object.defineProperty(f, 'size', { value: size });
  return f;
};

describe('validateBoundaryFile', () => {
  it('accepts .geojson, .json and .kml within 5 MB (any case)', () => {
    for (const n of ['a.geojson', 'a.json', 'a.kml', 'A.GeoJSON', 'b.KML']) expect(validateBoundaryFile(file(n, 1024))).toBeNull();
  });
  it('accepts exactly 5 MB and rejects one byte more', () => {
    expect(MAX_BOUNDARY_BYTES).toBe(5 * 1024 * 1024);
    expect(validateBoundaryFile(file('a.geojson', MAX_BOUNDARY_BYTES))).toBeNull();
    expect(validateBoundaryFile(file('a.geojson', MAX_BOUNDARY_BYTES + 1))).toMatch(/5 MB/);
  });
  it('rejects other file types', () => {
    for (const n of ['a.shp', 'a.zip', 'a.txt', 'geojson', 'a.geojson.exe', 'a.kmz']) expect(validateBoundaryFile(file(n, 10)), n).toMatch(/GeoJSON|KML/);
  });
  it('rejects empty files and a missing file', () => {
    expect(validateBoundaryFile(file('a.geojson', 0))).toMatch(/empty/i);
    expect(validateBoundaryFile(null)).toMatch(/choose/i);
  });
});

import { validateProjectFields, validateYear } from '../src/features/projects/validate';

describe('project field validation', () => {
  it('accepts 1970 to 2100 integers only', () => {
    for (const y of ['1970', '2011', '2100']) expect(validateYear(y)).toBeNull();
    for (const y of ['1969', '2101', '20.5', '', 'abcd', '19999']) expect(validateYear(y), y).not.toBeNull();
  });
  it('checks required fields, 100-char limits and the file', () => {
    const f = new File(['x'], 'a.geojson');
    const ok = { name: 'n', country: 'c', ecosystem: 'forest / woodland', intervention: 'i', year: '1975', file: f };
    expect(validateProjectFields(ok)).toEqual({});
    const bad = validateProjectFields({ ...ok, name: ' ', ecosystem: 'x'.repeat(101), intervention: 'y'.repeat(101), file: null });
    expect(Object.keys(bad).sort()).toEqual(['ecosystem', 'file', 'intervention', 'name']);
  });
});
