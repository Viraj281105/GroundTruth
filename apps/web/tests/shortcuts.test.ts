import { describe, expect, it } from 'vitest';
import { matchShortcut, type KeyInfo } from '../src/lib/shortcuts-core';

const key = (k: string, over: Partial<KeyInfo> = {}): KeyInfo => ({ key: k, ctrlKey: false, metaKey: false, altKey: false, typing: false, ...over });

describe('shortcuts', () => {
  it('Ctrl/Cmd+K opens the palette even while typing', () => {
    expect(matchShortcut(false, key('k', { ctrlKey: true, typing: true })).result.type).toBe('palette');
    expect(matchShortcut(false, key('K', { metaKey: true })).result.type).toBe('palette');
  });

  it('ignores plain keys while typing', () => {
    expect(matchShortcut(false, key('t', { typing: true })).result.type).toBe('none');
    expect(matchShortcut(false, key('?', { typing: true })).result.type).toBe('none');
  });

  it('g then a letter navigates, and g alone waits', () => {
    const first = matchShortcut(false, key('g'));
    expect(first).toEqual({ result: { type: 'pending' }, pending: true });
    expect(matchShortcut(true, key('c')).result).toEqual({ type: 'navigate', href: '/cases' });
    expect(matchShortcut(true, key('z')).result.type).toBe('none');
  });

  it('? shows help; t and v cycle theme and lens', () => {
    expect(matchShortcut(false, key('?')).result.type).toBe('help');
    expect(matchShortcut(false, key('t')).result.type).toBe('theme');
    expect(matchShortcut(false, key('v')).result.type).toBe('lens');
  });

  it('does not hijack browser shortcuts', () => {
    expect(matchShortcut(false, key('t', { ctrlKey: true })).result.type).toBe('none');
    expect(matchShortcut(false, key('c', { altKey: true })).result.type).toBe('none');
  });
});
