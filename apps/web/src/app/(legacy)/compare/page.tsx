import React, { Suspense } from 'react';
import { ComparePage } from '../../../features/compare/ComparePage';

export const metadata = { title: 'Compare cases' };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ComparePage />
    </Suspense>
  );
}
