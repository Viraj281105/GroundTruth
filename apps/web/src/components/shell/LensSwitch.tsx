'use client';

import React, { useId, useRef } from 'react';
import { useLens } from '../../lib/lens';
import { useToast } from '../ds/Overlay';
import { LENSES, LENS_DESCRIPTIONS, nextLens } from '../../lib/lens-core';
import { t } from '../../lib/i18n';
import styles from './Toggles.module.css';

/** Segmented control: how much detail pages reveal (Story, Explorer, Auditor). A radio group with arrow-key support. */
export function LensSwitch() {
  const { lens, setLens } = useLens();
  const toast = useToast();
  const group = useRef<HTMLDivElement>(null);
  const descId = useId();
  const choose = (name: (typeof LENSES)[number]) => {
    setLens(name);
    toast(LENS_DESCRIPTIONS[name]);
  };
  return (
    <div
      ref={group}
      className={styles.segmented}
      role="radiogroup"
      aria-label="How much detail to show"
      aria-describedby={descId}
      onKeyDown={(e) => {
        const next = nextLens(lens, e.key);
        if (!next) return;
        e.preventDefault();
        choose(next);
        group.current?.querySelector<HTMLElement>(`[data-lens="${next}"]`)?.focus();
      }}
    >
      <span id={descId} className="sr-only">
        {LENS_DESCRIPTIONS[lens]}
      </span>
      {LENSES.map((name) => (
        <button
          key={name}
          type="button"
          role="radio"
          data-lens={name}
          aria-checked={lens === name}
          tabIndex={lens === name ? 0 : -1}
          className={`${styles.segment} ${lens === name ? styles.segmentOn : ''}`}
          onClick={() => choose(name)}
          title={LENS_DESCRIPTIONS[name]}
          aria-label={`${t(`lens.${name}`)}. ${LENS_DESCRIPTIONS[name]}`}
        >
          {t(`lens.${name}`)}
        </button>
      ))}
    </div>
  );
}
