'use client';

import React, { useEffect, useRef, useState } from 'react';

/** Counts from 0 to `value` when scrolled into view. Shows the final value at once under reduced motion. */
export function CountUp({ value, decimals = 0, suffix = '', duration = 1100 }: { value: number; decimals?: number; suffix?: string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(value);
  const done = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    setShown(0);
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting || done.current) return;
        done.current = true;
        io.disconnect();
        const start = performance.now();
        const step = (now: number) => {
          const t = Math.min((now - start) / duration, 1);
          const eased = 1 - (1 - t) ** 3;
          setShown(value * eased);
          if (t < 1) requestAnimationFrame(step);
          else setShown(value);
        };
        requestAnimationFrame(step);
        // Throttled tabs may never run a frame: land on the final value anyway.
        window.setTimeout(() => setShown(value), duration + 400);
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [value, duration]);

  return (
    <span ref={ref} className="num">
      {shown.toFixed(decimals)}
      {suffix}
    </span>
  );
}
