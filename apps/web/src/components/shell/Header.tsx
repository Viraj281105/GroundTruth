'use client';

import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu, Search, X } from 'lucide-react';
import { Chip } from '../ds/Chip';
import { ThemeToggle } from './ThemeToggle';
import { UserMenu } from './UserMenu';
import { OPEN_PALETTE_EVENT } from './ShellOverlays';
import { t } from '../../lib/i18n';
import styles from './Header.module.css';

const NAV = [
  { href: '/cases', key: 'nav.cases' },
  { href: '/compare', key: 'nav.compare' },
  { href: '/claims', key: 'nav.claims' },
] as const;

function BrandMark() {
  return (
    <svg className={styles.mark} width="30" height="30" viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <rect width="28" height="28" rx="9" fill="var(--accent)" />
      <path d="M6 18 C10 18 12 15 14 13 C16 11 18 8 22 8" stroke="var(--text-on-accent)" strokeWidth="2" strokeLinecap="round" />
      <path d="M6 18 C10 18 12 17 14 17 C16 17 18 18 22 18" stroke="var(--text-on-accent)" strokeWidth="2" strokeLinecap="round" strokeDasharray="1 3.2" opacity="0.85" />
    </svg>
  );
}

const isActive = (pathname: string, href: string) => pathname === href || pathname.startsWith(`${href}/`);

export function Header() {
  const pathname = usePathname() ?? '/';
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const pill = useRef<HTMLElement>(null);
  const [slider, setSlider] = useState<{ left: number; width: number } | null>(null);

  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  // Slide the active indicator under the current link; recompute on resize and font load.
  useLayoutEffect(() => {
    const measure = () => {
      const nav = pill.current;
      const el = nav?.querySelector<HTMLElement>('[aria-current="page"]');
      setSlider(el && nav ? { left: el.offsetLeft, width: el.offsetWidth } : null);
    };
    measure();
    window.addEventListener('resize', measure);
    void document.fonts?.ready.then(measure);
    return () => window.removeEventListener('resize', measure);
  }, [pathname]);

  return (
    <header className={`${styles.header} ${scrolled ? styles.scrolled : ''}`}>
      <div className={`gt-container ${styles.bar}`}>
        <Link href="/" className={styles.brand} aria-label="GroundTruth home">
          <BrandMark />
          <span className={styles.wordmark}>GroundTruth</span>
        </Link>

        <nav ref={pill} className={styles.pill} aria-label="Primary">
          {slider && <span className={styles.slider} style={{ transform: `translateX(${slider.left}px)`, width: slider.width }} aria-hidden="true" />}
          {NAV.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <Link key={item.href} href={item.href} className={`${styles.link} ${active ? styles.active : ''}`} aria-current={active ? 'page' : undefined}>
                {t(item.key)}
              </Link>
            );
          })}
        </nav>

        <div className={styles.tools}>
          <Chip tone="sim" dot title={t('sim.explain')} className={styles.sim}>
            {t('sim.chip')}
          </Chip>
          <button type="button" className={`${styles.iconBtn} ${styles.hideSm}`} onClick={() => window.dispatchEvent(new Event(OPEN_PALETTE_EVENT))} aria-label="Search (Ctrl or Command K)" title="Search · Ctrl/⌘ K">
            <Search size={17} aria-hidden="true" />
          </button>
          <span className={styles.hideSm}>
            <ThemeToggle />
          </span>
          <UserMenu />
          <button type="button" className={`${styles.iconBtn} ${styles.menuBtn}`} onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-label="Menu">
            {open ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </div>

      {open && (
        <nav className={styles.sheet} aria-label="Mobile">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} className={`${styles.sheetLink} ${isActive(pathname, item.href) ? styles.sheetActive : ''}`}>
              {t(item.key)}
            </Link>
          ))}
          <div className={styles.sheetTools}>
            <button type="button" className={styles.sheetSearch} onClick={() => { setOpen(false); window.dispatchEvent(new Event(OPEN_PALETTE_EVENT)); }}>
              <Search size={16} aria-hidden="true" /> Search
            </button>
            <ThemeToggle />
          </div>
        </nav>
      )}
    </header>
  );
}
