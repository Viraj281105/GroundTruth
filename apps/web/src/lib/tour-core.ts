/** Pure tour logic: steps, a tiny reducer and persistence that never throws and never needs storage. */

export const TOUR_STORAGE_KEY = 'gt-tour-seen';
export const OPEN_TOUR_EVENT = 'gt:open-tour';

export interface TourStep {
  title: string;
  body: string;
}

export const TOUR_STEPS: readonly TourStep[] = [
  // The first two steps describe what a signed-in user can actually do today. They used to promise a
  // counterfactual estimate (not available for a user's own project) and said no real project had been
  // analysed (untrue once a project has ingested Sentinel-2 observations).
  { title: 'Welcome to GroundTruth', body: 'GroundTruth checks what a restoration project claims against what can actually be observed: satellite measurements inside the project boundary, the documents you upload, and a record of where every number came from.' },
  { title: 'Measured, simulated or unavailable: always labelled', body: 'Your own projects use real Sentinel-2 observations. Benchmark cases that run on a simulated fixture carry a violet “Simulated data” label. Anything that could not be measured is shown as unavailable, never filled in.' },
  { title: 'Choose how much detail you want', body: 'Story keeps it plain. Explorer adds interactive evidence. Auditor shows every diagnostic and the full provenance. Switch any time from the top bar.' },
  { title: 'Move fast', body: 'Press Ctrl/⌘ K to jump anywhere, or press ? for every shortcut. You can replay this tour from the account menu or the footer.' },
];

export interface TourState {
  step: number;
}

export type TourAction = 'next' | 'back' | 'reset';

export function tourReducer(state: TourState, action: TourAction, total = TOUR_STEPS.length): TourState {
  if (action === 'reset') return { step: 0 };
  if (action === 'next') return { step: Math.min(state.step + 1, total - 1) };
  return { step: Math.max(state.step - 1, 0) };
}

/** Routes where the sign-in and register forms live: the tour never opens on its own there. */
export function tourSuppressedOn(pathname: string): boolean {
  return /^\/(login|register|sign-in)(\/|$)/.test(pathname);
}

/** Session-level memory, so a blocked or full localStorage still means "once per visit", not "every navigation". */
let sessionSeen = false;

export function hasSeenTour(storage: Pick<Storage, 'getItem'> | null | undefined): boolean {
  if (sessionSeen) return true;
  try {
    if (storage && storage.getItem(TOUR_STORAGE_KEY)) return true;
  } catch {
    /* storage blocked: rely on session memory */
  }
  return false;
}

export function markTourSeen(storage: Pick<Storage, 'setItem'> | null | undefined): void {
  sessionSeen = true;
  try {
    storage?.setItem(TOUR_STORAGE_KEY, '1');
  } catch {
    /* session memory still prevents a repeat within this visit */
  }
}

/** For tests. */
export function resetTourSessionMemory(): void {
  sessionSeen = false;
}

export function safeLocalStorage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}
