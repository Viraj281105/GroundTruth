'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu, Search, X } from 'lucide-react';
import { OPEN_PALETTE_EVENT } from './ShellOverlays';
import { Chip } from '../ds/Chip';
import { ThemeToggle } from './ThemeToggle';
import { LensSwitch } from './LensSwitch';
import { t } from '../../lib/i18n';
import styles from './Header.module.css';

const NAV = [
  { href: '/cases', key: 'nav.cases' },
  { href: '/compare', key: 'nav.compare' },
  { href: '/claims', key: 'nav.claims' },
  { href: '/method', key: 'nav.method' },
  { href: '/status', key: 'nav.status' },
] as const;

function BrandMark() {
  return (
    <svg className={styles.mark} width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <rect width="28" height="28" rx="8" fill="var(--accent)" />
      <path d="M6 18 C10 18 12 15 14 13 C16 11 18 8 22 8" stroke="var(--text-on-accent)" strokeWidth="2" strokeLinecap="round" />
      <path d="M6 18 C10 18 12 17 14 17 C16 17 18 18 22 18" stroke="var(--text-on-accent)" strokeWidth="2" strokeLinecap="round" strokeDasharray="1 3.2" opacity="0.85" />
    </svg>
  );
}

export function Header() {
  const pathname = usePathname() ?? '/';
  const [open, setOpen] = useState(false);

  useEffect(() => setOpen(false), [pathname]);

  return (
    <header className={styles.header}>
      <div className={`gt-container ${styles.bar}`}>
        <Link href="/" className={styles.brand} aria-label="GroundTruth home">
          <BrandMark />
          <span className={styles.wordmark}>GroundTruth</span>
        </Link>

        <nav className={`${styles.nav} ${open ? styles.navOpen : ''}`} aria-label="Primary">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link key={item.href} href={item.href} className={`${styles.link} ${active ? styles.active : ''}`} aria-current={active ? 'page' : undefined}>
                {t(item.key)}
              </Link>
            );
          })}
        </nav>

        <div className={styles.tools}>
          <Chip tone="sim" dot title={t('sim.explain')}>
            {t('sim.chip')}
          </Chip>
          <button type="button" className={styles.search} onClick={() => window.dispatchEvent(new Event(OPEN_PALETTE_EVENT))} aria-label="Open command palette">
            <Search size={16} aria-hidden="true" />
            <span className={styles.searchLabel}>Search</span>
            <kbd>⌘K</kbd>
          </button>
          <div className={styles.lens}>
            <LensSwitch />
          </div>
          <ThemeToggle />
          <button type="button" className={styles.menu} onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-label="Menu">
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>
    </header>
  );
}
