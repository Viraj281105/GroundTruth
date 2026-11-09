'use client';

import React from 'react';
import { OPEN_TOUR_EVENT } from '../../lib/tour-core';

/** Opens the welcome tour again from anywhere in the shell (listened for by ShellOverlays). */
export function TourButton({ className, children = 'Show the tour again', onDone, role }: { className?: string; children?: React.ReactNode; onDone?: () => void; role?: string }) {
  return (
    <button
      type="button"
      className={className}
      role={role}
      onClick={() => {
        window.dispatchEvent(new Event(OPEN_TOUR_EVENT));
        onDone?.();
      }}
    >
      {children}
    </button>
  );
}
