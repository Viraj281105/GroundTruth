import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a>,
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: () => undefined, replace: () => undefined, refresh: () => undefined }),
  usePathname: () => '/app/demo/dashboard',
}));

import { AppSidebar } from '../src/components/shell/AppSidebar';
import { MobileTabBar } from '../src/components/shell/MobileTabBar';
import { LensSwitch } from '../src/components/shell/LensSwitch';
import { ThemeToggle } from '../src/components/shell/ThemeToggle';
import { Header } from '../src/components/shell/Header';
import { LENSES, LENS_DESCRIPTIONS, nextLens } from '../src/lib/lens-core';

const org = { id: 'o1', slug: 'demo', name: 'Demo NGO', type: 'ngo', role: 'owner' } as never;

/** Accessible name of every link and button in the markup: aria-label, else visible text (icons excluded). */
function namesOf(markup: string, tag: 'a' | 'button'): string[] {
  const out: string[] = [];
  const re = new RegExp(`<${tag}\\b([^>]*)>([\\s\\S]*?)</${tag}>`, 'g');
  for (const m of markup.matchAll(re)) {
    const label = /aria-label="([^"]*)"/.exec(m[1])?.[1];
    const text = m[2]
      .replace(/<svg[\s\S]*?<\/svg>/g, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    out.push((label ?? text).trim());
  }
  return out;
}

describe('shell accessibility', () => {
  it('every sidebar link and button has a non-empty accessible name', () => {
    const html = renderToStaticMarkup(<AppSidebar orgs={[org]} active={org} />);
    const names = [...namesOf(html, 'a'), ...namesOf(html, 'button')];
    expect(names.length).toBeGreaterThan(5);
    for (const n of names) expect(n, JSON.stringify(names)).not.toBe('');
    // Named explicitly, so the name survives the collapsed (icon-only) sidebar.
    expect(html).toContain('aria-label="Projects"');
    expect(html).toContain('aria-label="Overview"');
  });

  it('marks exactly the current page with aria-current="page" and labels the landmarks', () => {
    const html = renderToStaticMarkup(<AppSidebar orgs={[org]} active={org} />);
    expect(html.match(/aria-current="page"/g)).toHaveLength(1);
    expect(/<a[^>]*href="\/app\/demo\/dashboard"[^>]*aria-current="page"|<a[^>]*aria-current="page"[^>]*href="\/app\/demo\/dashboard"/.test(html)).toBe(true);
    expect(html).toMatch(/<nav[^>]*aria-label="Main"/);
    expect(html).toMatch(/<aside[^>]*aria-label=/);
  });

  it('names the mobile tabs, the theme toggle and the public header controls', () => {
    const mobile = renderToStaticMarkup(<MobileTabBar orgs={[org]} active={org} />);
    for (const n of [...namesOf(mobile, 'a'), ...namesOf(mobile, 'button')]) expect(n).not.toBe('');
    expect(mobile).toMatch(/<nav[^>]*aria-label="Primary mobile"/);
    for (const n of namesOf(renderToStaticMarkup(<ThemeToggle />), 'button')) expect(n).not.toBe('');
    const header = renderToStaticMarkup(<Header />);
    for (const n of [...namesOf(header, 'a'), ...namesOf(header, 'button')]) expect(n).not.toBe('');
    expect(header).toMatch(/<nav[^>]*aria-label="Primary"/);
  });
});

describe('detail-level switch', () => {
  it('is a radio group where each option explains itself in plain words', () => {
    const html = renderToStaticMarkup(<LensSwitch />);
    expect(html).toContain('role="radiogroup"');
    expect(html.match(/role="radio"/g)).toHaveLength(LENSES.length);
    for (const lens of LENSES) expect(html).toContain(LENS_DESCRIPTIONS[lens].replace(/'/g, '&#x27;'));
    for (const n of namesOf(html, 'button')) expect(n).not.toBe('');
    expect(html.match(/tabindex="0"/g)).toHaveLength(1); // roving tabindex
  });

  it('moves between options with the arrow keys, wrapping at the ends', () => {
    expect(nextLens('story', 'ArrowRight')).toBe('explorer');
    expect(nextLens('auditor', 'ArrowRight')).toBe('story');
    expect(nextLens('story', 'ArrowLeft')).toBe('auditor');
    expect(nextLens('explorer', 'Home')).toBe('story');
    expect(nextLens('explorer', 'End')).toBe('auditor');
    expect(nextLens('explorer', 'a')).toBeNull();
  });
});
