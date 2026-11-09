'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Dialog, useToast } from '../ds/Overlay';
import { CommandPalette } from './CommandPalette';
import { Tour } from './Tour';
import { OPEN_TOUR_EVENT, hasSeenTour, markTourSeen, safeLocalStorage, tourSuppressedOn } from '../../lib/tour-core';
import { useTheme } from '../../lib/theme';
import { useLens } from '../../lib/lens';
import { LENSES, type Lens } from '../../lib/lens-core';
import type { ThemePreference } from '../../lib/theme-core';
import { matchShortcut, SHORTCUT_HELP } from '../../lib/shortcuts-core';
import { RECENT_STORAGE_KEY, addRecent, caseIdFromPath, parseRecent } from '../../lib/recent-core';
import { getCases } from '../../lib/api';
import type { PaletteCase } from '../../lib/palette-core';
import styles from './CommandPalette.module.css';

export const OPEN_PALETTE_EVENT = 'gt:open-palette';

/** Palette, shortcuts, help, first-run tour and recently-viewed tracking, mounted once for the whole app. */
export function ShellOverlays() {
  const router = useRouter();
  const pathname = usePathname() ?? '/';
  const toast = useToast();
  const { theme, setTheme } = useTheme();
  const { lens, setLens } = useLens();

  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  const [tour, setTour] = useState(false);
  const [cases, setCases] = useState<PaletteCase[]>([]);
  const [recent, setRecent] = useState<string[]>([]);
  const loaded = useRef(false);
  const pending = useRef(false);

  // Recently viewed + first-run tour.
  useEffect(() => {
    try {
      setRecent(parseRecent(window.localStorage.getItem(RECENT_STORAGE_KEY)));
    } catch {
      /* storage blocked: no recents */
    }
    // First-run tour: once per browser (localStorage) or at least once per visit (memory). Never over the sign-in forms.
    if (!hasSeenTour(safeLocalStorage()) && !tourSuppressedOn(window.location.pathname)) setTour(true);
  }, []);

  const closeTour = useCallback(() => {
    markTourSeen(safeLocalStorage());
    setTour(false);
  }, []);

  useEffect(() => {
    const id = caseIdFromPath(pathname);
    if (!id) return;
    setRecent((prev) => {
      const next = addRecent(prev, id);
      try {
        window.localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, [pathname]);

  // Load case names lazily the first time the palette opens.
  useEffect(() => {
    if (!palette || loaded.current) return;
    loaded.current = true;
    getCases()
      .then((res) => setCases(res.data.map((c) => ({ id: c.case_id, name: c.name }))))
      .catch(() => {
        loaded.current = false; // try again next time; pages still work without it
      });
  }, [palette]);

  const cycleTheme = useCallback(() => {
    const order: ThemePreference[] = ['light', 'dark', 'system'];
    const next = order[(order.indexOf(theme) + 1) % order.length];
    setTheme(next);
    toast(`Theme: ${next}`);
  }, [theme, setTheme, toast]);

  const cycleLens = useCallback(() => {
    const next = LENSES[(LENSES.indexOf(lens) + 1) % LENSES.length];
    setLens(next);
    toast(`Detail level: ${next}`);
  }, [lens, setLens, toast]);

  const onAction = useCallback(
    (action: string) => {
      if (action.startsWith('theme:')) setTheme(action.slice(6) as ThemePreference);
      else if (action.startsWith('lens:')) setLens(action.slice(5) as Lens);
      else if (action === 'tour') setTour(true);
      else if (action === 'shortcuts') setHelp(true);
    },
    [setTheme, setLens],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = Boolean(target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)));
      const { result, pending: next } = matchShortcut(pending.current, {
        key: e.key,
        ctrlKey: e.ctrlKey,
        metaKey: e.metaKey,
        altKey: e.altKey,
        typing,
      });
      pending.current = next;
      if (result.type === 'none' || result.type === 'pending') return;
      e.preventDefault();
      if (result.type === 'palette') setPalette(true);
      else if (result.type === 'help') setHelp(true);
      else if (result.type === 'theme') cycleTheme();
      else if (result.type === 'lens') cycleLens();
      else if (result.type === 'navigate') router.push(result.href);
    };
    const onOpen = () => setPalette(true);
    const onTour = () => setTour(true);
    window.addEventListener('keydown', onKey);
    window.addEventListener(OPEN_PALETTE_EVENT, onOpen);
    window.addEventListener(OPEN_TOUR_EVENT, onTour);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener(OPEN_PALETTE_EVENT, onOpen);
      window.removeEventListener(OPEN_TOUR_EVENT, onTour);
    };
  }, [router, cycleTheme, cycleLens]);

  return (
    <>
      <CommandPalette open={palette} onClose={() => setPalette(false)} cases={cases} recent={recent} onAction={onAction} />
      <Tour open={tour} onClose={closeTour} />
      <Dialog open={help} onClose={() => setHelp(false)} title="Keyboard shortcuts">
        <ul className={styles.list} style={{ maxHeight: 'none' }}>
          {SHORTCUT_HELP.map((row) => (
            <li key={row.keys} className={styles.item} style={{ cursor: 'default' }}>
              <span>{row.does}</span>
              <kbd>{row.keys}</kbd>
            </li>
          ))}
        </ul>
      </Dialog>
    </>
  );
}
