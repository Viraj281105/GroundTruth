import React from 'react';
import { StatusView } from '../../features/status/StatusView';
import { RequireRole } from '../../features/auth/RequireAuth';

export const metadata = { title: 'System status' };

export default function Page() {
  return (
    <RequireRole minimum="dev">
      <StatusView />
    </RequireRole>
  );
}
