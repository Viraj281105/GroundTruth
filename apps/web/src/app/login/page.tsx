import React, { Suspense } from 'react';
import { LoginForm } from '../../features/auth/AuthForms';

export const metadata = { title: 'Sign in' };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
