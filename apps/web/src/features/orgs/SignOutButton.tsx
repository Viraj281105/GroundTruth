'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '../../components/ds/Button';
import { useAuth } from '../../lib/auth';

/** Ends the session through the existing auth provider, then returns to the public site. */
export function SignOutButton() {
  const { signOut } = useAuth();
  const router = useRouter();
  return (
    <Button
      variant="ghost"
      onClick={async () => {
        await signOut();
        router.push('/');
        router.refresh();
      }}
    >
      Sign out
    </Button>
  );
}
