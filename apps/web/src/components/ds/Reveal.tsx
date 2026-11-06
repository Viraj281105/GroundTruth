'use client';

import React, { useEffect, useRef, useState } from 'react';

export type RevealVariant = 'up' | 'left' | 'right' | 'scale' | 'fade';

/**
 * Reveals its children when scrolled into view (fade plus a short slide or scale).
 * Without JavaScript, or under prefers-reduced-motion, content is simply visible:
 * the hidden state only exists under the `js` class and outside reduced motion.
 */
export function Reveal({
  children,
  variant = 'up',
  delay = 0,
  as: Tag = 'div',
  className = '',
  once = true,
}: {
  children: React.ReactNode;
  variant?: RevealVariant;
  /** Milliseconds; use multiples of ~80 to stagger siblings. */
  delay?: number;
  as?: React.ElementType;
  className?: string;
  once?: boolean;
}) {
  const ref = useRef<HTMLElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      setShown(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setShown(true);
            if (once) io.disconnect();
          } else if (!once) setShown(false);
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -6% 0px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [once]);

  return (
    <Tag ref={ref} className={className} data-reveal={variant} data-in={shown ? '' : undefined} style={{ '--reveal-delay': `${delay}ms` } as React.CSSProperties}>
      {children}
    </Tag>
  );
}
