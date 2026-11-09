/** Pure lens logic. The lens controls how much detail a page reveals (progressive disclosure). */

export type Lens = 'story' | 'explorer' | 'auditor';

export const LENSES: readonly Lens[] = ['story', 'explorer', 'auditor'];
export const DEFAULT_LENS: Lens = 'explorer';
export const LENS_STORAGE_KEY = 'gt-lens';

const DEPTH: Record<Lens, number> = { story: 0, explorer: 1, auditor: 2 };

export function parseLens(raw: string | null | undefined): Lens | null {
  return raw === 'story' || raw === 'explorer' || raw === 'auditor' ? raw : null;
}

/** URL override (`?lens=`) beats the stored choice, which beats the default. */
export function resolveLens(urlValue: string | null, storedValue: string | null): Lens {
  return parseLens(urlValue) ?? parseLens(storedValue) ?? DEFAULT_LENS;
}

/** Content tagged `required` is visible in that lens and every deeper one. */
export function lensIncludes(current: Lens, required: Lens): boolean {
  return DEPTH[current] >= DEPTH[required];
}

/** What each level of detail does, in plain words for non-technical readers. */
export const LENS_DESCRIPTIONS: Record<Lens, string> = {
  story: 'Story: the short version. Plain-language results with one number and one chart.',
  explorer: 'Explorer: adds interactive charts, the comparison areas and the checks behind the result.',
  auditor: 'Auditor: everything, including technical details, record IDs and fingerprints, for reviewers.',
};

/** Arrow-key movement inside the segmented control (wraps around). */
export function nextLens(current: Lens, key: string): Lens | null {
  const i = LENSES.indexOf(current);
  if (key === 'ArrowRight' || key === 'ArrowDown') return LENSES[(i + 1) % LENSES.length];
  if (key === 'ArrowLeft' || key === 'ArrowUp') return LENSES[(i - 1 + LENSES.length) % LENSES.length];
  if (key === 'Home') return LENSES[0];
  if (key === 'End') return LENSES[LENSES.length - 1];
  return null;
}
