import React from 'react';
import { ClaimsWorkbench } from '../../features/claims/ClaimsWorkbench';
import { RequireAuth } from '../../features/auth/RequireAuth';

export const metadata = { title: 'Claims workbench' };

export default function Page() {
  return (
    <RequireAuth action="use the claims workbench">
      <ClaimsWorkbench />
    </RequireAuth>
  );
}
