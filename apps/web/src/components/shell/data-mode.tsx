'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { DataMode } from '../ds/DataModeBanner';

interface DataModeContextValue {
  mode: DataMode;
  setMode: (mode: DataMode) => void;
}

const DataModeContext = createContext<DataModeContextValue>({ mode: 'observed', setMode: () => undefined });

/**
 * Holds the data mode of whatever the current page shows. The shell renders the persistent banner from
 * it (R7). "observed" is the default and renders nothing; pages showing synthetic data set "simulated".
 */
export function DataModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<DataMode>('observed');
  const setMode = useCallback((next: DataMode) => setModeState(next), []);
  const value = useMemo(() => ({ mode, setMode }), [mode, setMode]);
  return <DataModeContext.Provider value={value}>{children}</DataModeContext.Provider>;
}

export function useDataMode(): DataModeContextValue {
  return useContext(DataModeContext);
}

/** Drop into a page or layout: declares its data mode while mounted, then reverts to "observed". */
export function SetDataMode({ mode }: { mode: DataMode }) {
  const { setMode } = useDataMode();
  useEffect(() => {
    setMode(mode);
    return () => setMode('observed');
  }, [mode, setMode]);
  return null;
}
