/** Global keyboard shortcuts: pure matching so the rules are testable. */

export type ShortcutResult =
  | { type: 'navigate'; href: string }
  | { type: 'palette' }
  | { type: 'help' }
  | { type: 'theme' }
  | { type: 'lens' }
  | { type: 'pending' }
  | { type: 'none' };

export interface KeyInfo {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  /** True when focus is in an input, textarea, select or contenteditable. */
  typing: boolean;
}

const GO: Record<string, string> = { h: '/', c: '/cases', x: '/compare', l: '/claims', m: '/method', s: '/status' };

export const SHORTCUT_HELP: ReadonlyArray<{ keys: string; does: string }> = [
  { keys: 'Ctrl/⌘ K', does: 'Open the command palette' },
  { keys: '?', does: 'Show this help' },
  { keys: 'g then h', does: 'Go to Home' },
  { keys: 'g then c', does: 'Go to Cases' },
  { keys: 'g then x', does: 'Go to Compare' },
  { keys: 'g then l', does: 'Go to Claims' },
  { keys: 'g then m', does: 'Go to How it works' },
  { keys: 'g then s', does: 'Go to Status' },
  { keys: 't', does: 'Cycle theme' },
  { keys: 'v', does: 'Cycle detail level (Story, Explorer, Auditor)' },
];

/** `pending` is true when the previous key was `g`. Returns what to do and whether `g` is now pending. */
export function matchShortcut(pending: boolean, e: KeyInfo): { result: ShortcutResult; pending: boolean } {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') return { result: { type: 'palette' }, pending: false };
  if (e.typing || e.ctrlKey || e.metaKey || e.altKey) return { result: { type: 'none' }, pending: false };
  const key = e.key.toLowerCase();
  if (pending) {
    const href = GO[key];
    return { result: href ? { type: 'navigate', href } : { type: 'none' }, pending: false };
  }
  if (key === 'g') return { result: { type: 'pending' }, pending: true };
  if (e.key === '?') return { result: { type: 'help' }, pending: false };
  if (key === 't') return { result: { type: 'theme' }, pending: false };
  if (key === 'v') return { result: { type: 'lens' }, pending: false };
  return { result: { type: 'none' }, pending: false };
}
