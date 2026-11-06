'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { TabBar } from '../../../components/ds';
import { LensSwitch } from '../../../components/shell/LensSwitch';
import { layoutCopy } from './copy';
import { activeTabHref, caseTabLinks } from './tabs';

/** Route-based tabs with the detail-level switch beside them, where it actually applies. */
export function CaseTabs({ caseId }: { caseId: string }) {
  const pathname = usePathname() ?? '';
  const links = caseTabLinks(caseId);
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
      <div style={{ flex: '1 1 20rem', minWidth: 0 }}>
        <TabBar items={links} activeHref={activeTabHref(links, pathname)} label={layoutCopy.tabsLabel} />
      </div>
      <div style={{ paddingBottom: 'var(--space-2)' }}>
        <LensSwitch />
      </div>
    </div>
  );
}
