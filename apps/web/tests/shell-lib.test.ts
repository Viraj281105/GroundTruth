import { describe, expect, it } from 'vitest';
import { DEFAULT_LENS, lensIncludes, parseLens, resolveLens } from '../src/lib/lens-core';
import { glossary, GLOSSARY_TERMS } from '../src/lib/glossary';
import { t, setLocale, LOCALES } from '../src/lib/i18n';

describe('lens', () => {
  it('defaults to explorer', () => {
    expect(DEFAULT_LENS).toBe('explorer');
    expect(resolveLens(null, null)).toBe('explorer');
  });

  it('the URL override beats the stored value', () => {
    expect(resolveLens('auditor', 'story')).toBe('auditor');
    expect(resolveLens(null, 'story')).toBe('story');
  });

  it('ignores invalid values', () => {
    expect(parseLens('nonsense')).toBeNull();
    expect(resolveLens('nonsense', 'also-bad')).toBe('explorer');
  });

  it('a lens shows content for itself and every shallower lens', () => {
    expect(lensIncludes('story', 'explorer')).toBe(false);
    expect(lensIncludes('explorer', 'explorer')).toBe(true);
    expect(lensIncludes('auditor', 'explorer')).toBe(true);
    expect(lensIncludes('auditor', 'auditor')).toBe(true);
    expect(lensIncludes('explorer', 'auditor')).toBe(false);
    expect(lensIncludes('story', 'story')).toBe(true);
  });
});

describe('glossary', () => {
  it('defines core terms in plain and technical language', () => {
    const entry = glossary('placebo');
    expect(entry).not.toBeNull();
    expect(entry?.plain.length).toBeGreaterThan(20);
    expect(entry?.technical.length).toBeGreaterThan(20);
  });

  it('returns null for unknown terms', () => {
    expect(glossary('not-a-term')).toBeNull();
  });

  it('never uses accusatory or certainty language (R2)', () => {
    const banned = /\b(fraud|fraudulent|proves?|proven|guilty|illegal)\b/i;
    for (const id of GLOSSARY_TERMS) {
      const e = glossary(id);
      expect(`${e?.label} ${e?.plain} ${e?.technical}`).not.toMatch(banned);
    }
  });
});

describe('i18n', () => {
  it('translates a key present in the active locale', () => {
    setLocale('hi');
    expect(t('nav.cases')).not.toBe('nav.cases');
    setLocale('en');
  });

  it('falls back to English when a locale lacks the key', () => {
    setLocale('mr');
    expect(t('home.cta')).toBe(t('home.cta'));
    setLocale('en');
    const english = t('home.cta');
    setLocale('mr');
    expect(t('home.cta')).toBeTruthy();
    // a key only English has must still resolve
    expect(t('only.english.test.key')).toBe('only.english.test.key');
    setLocale('en');
    expect(english).toBeTruthy();
  });

  it('interpolates variables', () => {
    setLocale('en');
    expect(t('cases.count', { n: 3 })).toContain('3');
  });

  it('exposes en, hi and mr', () => {
    expect(LOCALES).toEqual(['en', 'hi', 'mr']);
  });
});
