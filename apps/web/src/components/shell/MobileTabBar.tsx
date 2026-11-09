'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Briefcase, FolderKanban, LayoutDashboard, MoreHorizontal } from 'lucide-react';
import type { Schemas } from '../../lib/api-client';
import { Dialog } from '../ds/Overlay';
import { NavGroups } from './AppSidebar';
import { OrgSwitcher } from './OrgSwitcher';
import { isNavActive, mobileTabs, navHref, navigationFor } from './navigation';
import styles from './OrgShell.module.css';

const TAB_ICONS = { dashboard: LayoutDashboard, projects: FolderKanban, portfolio: Briefcase } as const;

/** Below 768 px: a bottom tab bar for the main destinations and a sheet with the full navigation. */
export function MobileTabBar({ orgs, active }: { orgs: Schemas['OrgView'][]; active: Schemas['OrgView'] }) {
  const pathname = usePathname() ?? '';
  const [sheet, setSheet] = useState(false);
  const groups = navigationFor(active.type, active.role);
  const all = groups.flatMap((g) => g.items);
  const tabs = mobileTabs(groups);

  useEffect(() => setSheet(false), [pathname]);

  return (
    <>
      <nav className={styles.tabbar} aria-label="Primary mobile" style={{ gridTemplateColumns: `repeat(${tabs.length + 1}, 1fr)` }}>
        {tabs.map((it) => {
          const Icon = TAB_ICONS[it.id as keyof typeof TAB_ICONS];
          const body = (
            <>
              <Icon size={20} aria-hidden="true" />
              {it.label}
            </>
          );
          if (it.planned) {
            return (
              <span key={it.id} className={styles.tabPlanned} aria-disabled="true">
                {body}
              </span>
            );
          }
          return (
            <Link key={it.id} href={navHref(active.slug, it)} aria-current={isNavActive(pathname, active.slug, it, all) ? 'page' : undefined}>
              {body}
            </Link>
          );
        })}
        <button type="button" aria-haspopup="dialog" aria-expanded={sheet} onClick={() => setSheet(true)}>
          <MoreHorizontal size={20} aria-hidden="true" />
          More
        </button>
      </nav>
      <Dialog open={sheet} onClose={() => setSheet(false)} title="Navigation">
        <div className={styles.sheet}>
          <OrgSwitcher orgs={orgs} active={active} />
          <nav aria-label="Main (mobile)">
            <NavGroups groups={groups} orgSlug={active.slug} onNavigate={() => setSheet(false)} />
          </nav>
        </div>
      </Dialog>
    </>
  );
}

