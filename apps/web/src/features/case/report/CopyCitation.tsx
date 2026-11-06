'use client';

import React, { useState } from 'react';
import { Button, useToast } from '../../../components/ds';

/** Copies a ready-made citation string. Falls back to a visible message when the clipboard is blocked. */
export function CopyCitation({ citation }: { citation: string }) {
  const toast = useToast();
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(citation);
      setState('copied');
      toast('Citation copied');
    } catch {
      setState('failed');
    }
  };
  return (
    <span>
      <Button variant="secondary" onClick={copy}>
        {state === 'copied' ? 'Copied' : 'Copy citation'}
      </Button>
      {state === 'failed' && (
        <span role="alert"> Copying was blocked by the browser. Select the citation text above instead.</span>
      )}
    </span>
  );
}
