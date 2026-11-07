'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { DEFAULT_LENS, LENS_STORAGE_KEY, lensIncludes, resolveLens, type Lens as LensName } from './lens-core';

interface LensContextValue {
  lens: LensName;
  setLens: (lens: LensName) => void;
}

const LensContext = createContext<LensContextValue>({ lens: DEFAULT_LENS, setLens: () => undefined });

export function LensProvider({ children }: { children: React.ReactNode }) {
  const [lens, setLensState] = useState<LensName>(DEFAULT_LENS);

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(LENS_STORAGE_KEY);
    } catch {
      /* storage blocked */
    }
    setLensState(resolveLens(new URLSearchParams(window.location.search).get('lens'), stored));
  }, []);

  const setLens = useCallback((next: LensName) => {
    setLensState(next);
    try {
      window.localStorage.setItem(LENS_STORAGE_KEY, next);
    } catch {
      /* still applies for this visit */
    }
  }, []);

  const value = useMemo(() => ({ lens, setLens }), [lens, setLens]);
  return <LensContext.Provider value={value}>{children}</LensContext.Provider>;
}

export function useLens(): LensContextValue {
  return useContext(LensContext);
}

/** Renders children only when the current lens is at least `show`. */
export function Lens({ show, children }: { show: LensName; children: React.ReactNode }) {
  const { lens } = useLens();
  return lensIncludes(lens, show) ? <>{children}</> : null;
}
