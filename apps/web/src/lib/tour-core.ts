/** Pure tour logic: steps, a tiny reducer and persistence that never throws and never needs storage. */

export const TOUR_STORAGE_KEY = 'gt-tour-seen';
export const OPEN_TOUR_EVENT = 'gt:open-tour';

export interface TourStep {
  title: string;
  body: string;
}

export const TOUR_STEPS: readonly TourStep[] = [
  { title: 'Welcome to GroundTruth', body: 'We estimate what a restoration or carbon project actually achieved by comparing it with a blended “twin” built from similar land that was left alone.' },
  { title: 'Simulated data, always labelled', body: 'Demo cases run on a simulated test fixture. A violet “Simulated data” label stays on screen wherever that is so, and no real project has been analysed.' },
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
