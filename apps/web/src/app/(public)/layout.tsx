import React from 'react';
import { AppShell } from '../../components/shell/AppShell';

/** Marketing and sign-in pages: the public header and footer. Nothing here calls an authenticated API. */
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
