import React, { Suspense } from 'react';
import { RegisterForm } from '../../features/auth/AuthForms';

export const metadata = { title: 'Create account' };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <RegisterForm />
    </Suspense>
  );
}
