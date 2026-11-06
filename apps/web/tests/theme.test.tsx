import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { themeInitScript, resolveTheme, parseTheme, THEME_STORAGE_KEY } from '../src/lib/theme-core';
import { Chip } from '../src/components/ds/Chip';

describe('theme resolution', () => {
  it('resolves system from the OS preference', () => {
    expect(resolveTheme('system', true)).toBe('dark');
    expect(resolveTheme('system', false)).toBe('light');
  });

  it('an explicit choice wins over the OS preference', () => {
    expect(resolveTheme('light', true)).toBe('light');
    expect(resolveTheme('dark', false)).toBe('dark');
  });

  it('parses stored values and falls back to system for anything else', () => {
    expect(parseTheme('dark')).toBe('dark');
    expect(parseTheme('light')).toBe('light');
    expect(parseTheme('banana')).toBe('system');
    expect(parseTheme(null)).toBe('system');
  });
});

describe('pre-paint script', () => {
  it('reads the stored key and sets data-theme before hydration', () => {
    expect(themeInitScript).toContain(THEME_STORAGE_KEY);
    expect(themeInitScript).toContain('data-theme');
    expect(themeInitScript).toContain('prefers-color-scheme');
  });

  it('never throws when storage is unavailable', () => {
    expect(themeInitScript).toContain('try');
    expect(themeInitScript).toContain('catch');
  });
});

describe('simulated-data chip', () => {
  it('always says Simulated data', () => {
    const html = renderToStaticMarkup(<Chip tone="sim">Simulated data</Chip>);
    expect(html).toContain('Simulated data');
  });
});
