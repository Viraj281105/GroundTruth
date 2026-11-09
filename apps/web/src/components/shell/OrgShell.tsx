'use client';

import React, { useEffect, useState } from 'react';
import { PanelLeft, Search } from 'lucide-react';
import type { Schemas } from '../../lib/api-client';
import { DataModeBanner } from '../ds/DataModeBanner';
import { AppSidebar } from './AppSidebar';
import { DataModeProvider, useDataMode } from './data-mode';
import { LensSwitch } from './LensSwitch';
import { MobileTabBar } from './MobileTabBar';
import { OPEN_PALETTE_EVENT, ShellOverlays } from './ShellOverlays';
import { ThemeToggle } from './ThemeToggle';
import { UserMenu } from './UserMenu';
import styles from './OrgShell.module.css';

const COLLAPSE_KEY = 'gt-sidebar-collapsed';

function Banner() {
  const { mode } = useDataMode();
  return <DataModeBanner mode={mode} />;
}

/**
 * The role-aware app shell: collapsible sidebar (desktop), top bar, the persistent data-mode banner slot,
 * and a bottom tab bar with a navigation sheet below 768 px. Command palette, theme, language and the
 * detail-level (lens) preference live here unchanged; the lens is display density, never access control.
 */
export function OrgShell({ orgs, active, children }: { orgs: Schemas['OrgView'][]; active: Schemas['OrgView']; children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(COLLAPSE_KEY) === '1');
    } catch {
      /* storage blocked: stay expanded */
    }
  }, []);

  const toggle = () =>
    setCollapsed((c) => {
      try {
        window.localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1');
      } catch {
        /* ignore */
      }
      return !c;
    });

  return (
    <DataModeProvider>
      <a href="#main-content" className="gt-skip-link">
        Skip to main content
      </a>
      <div className={`${styles.app} ${collapsed ? styles.collapsed : ''}`}>
        <AppSidebar orgs={orgs} active={active} />
        <div className={styles.main}>
          <div className={styles.stick}>
            <Banner />
            <header className={styles.top}>
              <button type="button" className={`${styles.iconbtn} ${styles.hideMobile}`} onClick={toggle} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-pressed={collapsed}>
                <PanelLeft size={18} aria-hidden="true" />
              </button>
              <div className={styles.crumb}>
                <span>{active.name}</span>
              </div>
              <div className={styles.sp} />
              <button type="button" className={styles.cmd} onClick={() => window.dispatchEvent(new Event(OPEN_PALETTE_EVENT))} aria-label="Search Ctrl K">
                <Search size={15} aria-hidden="true" />
                <span className={styles.hideMobile}>Search</span>{' '}
                <kbd className={styles.hideMobile}>Ctrl K</kbd>
              </button>
              <span className={styles.hideMobile}>
                <LensSwitch />
              </span>
              <ThemeToggle />
              <UserMenu />
            </header>
          </div>
          <main id="main-content" className={styles.page}>
            {children}
          </main>
        </div>
      </div>
      <MobileTabBar orgs={orgs} active={active} />
      <ShellOverlays />
    </DataModeProvider>
  );
}
