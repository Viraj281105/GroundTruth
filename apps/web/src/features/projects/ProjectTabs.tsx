'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { TabBar } from '../../components/ds';
import { tabsFor, type AccessLevel } from './model';

export function ProjectTabs({ base, level }: { base: string; level: AccessLevel }) {
  const pathname = usePathname() ?? '';
  const items = tabsFor(level).map((t) => ({ href: `${base}/${t.segment}`, label: t.label }));
  const active = items.find((i) => pathname === i.href || pathname.startsWith(`${i.href}/`))?.href ?? items[0]!.href;
  return <TabBar items={items} activeHref={active} label="Project sections" />;
}
