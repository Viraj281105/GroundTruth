'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Briefcase,
  CheckCircle2,
  Database,
  FilePlus2,
  FileText,
  FolderKanban,
  LayoutDashboard,
  ScrollText,
  Share2,
  Sparkles,
  Users,
  type LucideIcon,
} from 'lucide-react';
import type { Schemas } from '../../lib/api-client';
import { OrgSwitcher } from './OrgSwitcher';
import { MEMBER_ROLE_LABELS, isNavActive, navHref, navigationFor, type NavGroup, type NavIcon } from './navigation';
import styles from './OrgShell.module.css';

const ICONS: Record<NavIcon, LucideIcon> = {
  dashboard: LayoutDashboard,
  projects: FolderKanban,
  new: FilePlus2,
  portfolio: Briefcase,
  assessments: CheckCircle2,
  intelligence: Sparkles,
  evidence: Database,
  reports: FileText,
  members: Users,
  sharing: Share2,
  audit: ScrollText,
};

export function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" fill="none" aria-hidden="true" className={styles.mark}>
      <rect width="28" height="28" rx="7" fill="var(--accent)" />
      <path d="M6 18 C10 18 12 15 14 13 C16 11 18 8 22 8" stroke="var(--text-on-accent)" strokeWidth="2" strokeLinecap="round" />
      <path d="M6 18 C10 18 12 17 14 17 C16 17 18 18 22 18" stroke="var(--text-on-accent)" strokeWidth="2" strokeLinecap="round" strokeDasharray="1 3.2" opacity="0.85" />
    </svg>
  );
}

/** Grouped navigation, shared by the sidebar and the mobile sheet. Pages not built yet are shown, not linked. */
export function NavGroups({ groups, orgSlug, onNavigate }: { groups: NavGroup[]; orgSlug: string; onNavigate?: () => void }) {
  const pathname = usePathname() ?? '';
  const all = groups.flatMap((g) => g.items);
  return (
    <>
      {groups.map((g) => (
        <div className={styles.navgrp} key={g.id} role="group" aria-label={g.label}>
          <span className={styles.eyebrow}>{g.label}</span>
          {g.items.map((it) => {
            const Icon = ICONS[it.icon];
            if (it.planned) {
              return (
                <span key={it.id} className={`${styles.navi} ${styles.planned}`} aria-disabled="true">
                  <Icon size={18} aria-hidden="true" />
                  <span>{it.label}</span>
                  <em className={styles.tag}>Soon</em>
                </span>
              );
            }
            const active = isNavActive(pathname, orgSlug, it, all);
            return (
              <Link key={it.id} href={navHref(orgSlug, it)} className={styles.navi} aria-label={it.label} title={it.label} aria-current={active ? 'page' : undefined} onClick={onNavigate}>
                <Icon size={18} aria-hidden="true" />
                <span>{it.label}</span>
              </Link>
            );
          })}
        </div>
      ))}
    </>
  );
}

/** Desktop sidebar: brand, org switcher with perspective badge, grouped navigation, role footer. */
export function AppSidebar({ orgs, active }: { orgs: Schemas['OrgView'][]; active: Schemas['OrgView'] }) {
  const groups = navigationFor(active.type, active.role);
  return (
    <aside className={styles.side} aria-label="Sidebar">
      <Link href="/" className={styles.brand} aria-label="GroundTruth home">
        <BrandMark />
        <div className={styles.brandtxt}>
          <b>GroundTruth</b>{' '}
          <small>2.0</small>
        </div>
      </Link>
      <OrgSwitcher orgs={orgs} active={active} />
      <nav className={styles.nav} aria-label="Main">
        <NavGroups groups={groups} orgSlug={active.slug} />
      </nav>
      <div className={styles.sidefoot}>
        You are {MEMBER_ROLE_LABELS[active.role].toLowerCase()} of {active.name}. What you can open and change is decided by the server.
      </div>
    </aside>
  );
}
