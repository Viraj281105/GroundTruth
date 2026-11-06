'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { TabBar } from '../../../components/ds';
import { layoutCopy } from './copy';
import { activeTabHref, caseTabLinks } from './tabs';

/** Route-based tabs: the active one follows the URL, so deep links and back button work. */
export function CaseTabs({ caseId }: { caseId: string }) {
  const pathname = usePathname() ?? '';
  const links = caseTabLinks(caseId);
  return <TabBar items={links} activeHref={activeTabHref(links, pathname)} label={layoutCopy.tabsLabel} />;
}
