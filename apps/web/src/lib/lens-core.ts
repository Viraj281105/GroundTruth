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
