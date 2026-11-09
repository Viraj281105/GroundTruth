'use client';

import React from 'react';
import { UnavailablePanel } from '../../../../../../../components/ds/UnavailablePanel';

/** Route error boundary: a failure while rendering claim verification shows an honest message, never a blank crash. */
export default function VerificationError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div role="alert">
      <UnavailablePanel
        action={<button type="button" onClick={reset}>Try again</button>}
        title="Claim verification could not be displayed"
        reason="Something went wrong while loading this page. No claims or verification figures are shown, and nothing was changed."
        evidenceNeeded="Try again. If it keeps happening, report this reference to your administrator."
      />
      {error.digest && <p style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>Reference: {error.digest}</p>}
    </div>
  );
}
