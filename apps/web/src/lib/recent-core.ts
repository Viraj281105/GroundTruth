/** Recently viewed cases: pure list logic (storage lives in the component). */

export const RECENT_STORAGE_KEY = 'gt-recent';
export const MAX_RECENT = 6;

export function addRecent(list: string[], id: string): string[] {
  return [id, ...list.filter((existing) => existing !== id)].slice(0, MAX_RECENT);
}

export function parseRecent(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const value: unknown = JSON.parse(raw);
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string').slice(0, MAX_RECENT) : [];
  } catch {
    return [];
  }
}

/** `/cases/kariba-redd/evidence` -> `kariba-redd`; anything else -> null. */
export function caseIdFromPath(pathname: string): string | null {
  const match = /^\/cases\/([^/]+)/.exec(pathname);
  return match ? decodeURIComponent(match[1]) : null;
}
