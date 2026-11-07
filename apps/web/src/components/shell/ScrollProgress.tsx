'use client';

import React, { useEffect, useState } from 'react';

/** A thin reading-progress bar along the top edge. Decorative, hidden from assistive tech. */
export function ScrollProgress() {
  const [p, setP] = useState(0);
  useEffect(() => {
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setP(max > 0 ? Math.min(window.scrollY / max, 1) : 0);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);
  return (
    <div
      aria-hidden="true"
      style={{ position: 'fixed', insetInline: 0, top: 0, height: 3, zIndex: 90, transformOrigin: '0 50%', transform: `scaleX(${p})`, background: 'var(--accent)', opacity: p > 0.001 ? 1 : 0, pointerEvents: 'none' }}
    />
  );
}
