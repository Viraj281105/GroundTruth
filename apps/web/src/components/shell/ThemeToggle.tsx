'use client';

import React from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from '../../lib/theme';
import type { ThemePreference } from '../../lib/theme-core';
import { t } from '../../lib/i18n';
import styles from './Toggles.module.css';

const ORDER: ThemePreference[] = ['light', 'dark', 'system'];
const ICON = { light: Sun, dark: Moon, system: Monitor } as const;

/** Cycles light → dark → system. The label says what the next click does. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
  const Icon = ICON[theme];
  return (
    <button type="button" className={styles.iconButton} onClick={() => setTheme(next)} aria-label={`Theme: ${t(`theme.${theme}`)}. Switch to ${t(`theme.${next}`)}`} title={`Theme: ${t(`theme.${theme}`)}`}>
      <Icon size={18} />
    </button>
  );
}
