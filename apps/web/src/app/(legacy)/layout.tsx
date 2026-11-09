import React from 'react';
import { AppShell } from '../../components/shell/AppShell';

/**
 * Pre-2.0 pages (cases, claims, compare, status, admin, account) keep the original chrome until
 * later tasks migrate them into the org-scoped app. `/cases` itself now redirects to `/app`.
 */
export default function LegacyLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
