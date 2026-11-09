'use client';

import React, { useEffect, useId, useReducer, useRef } from 'react';
import { Button } from '../ds/Button';
import { TOUR_STEPS, TOUR_STORAGE_KEY, tourReducer } from '../../lib/tour-core';
import overlay from '../ds/Overlay.module.css';
import styles from './Tour.module.css';

export { TOUR_STORAGE_KEY };

/**
 * First-run tour as a modal native <dialog> (focus trap, Escape and focus return come from the browser).
 * The step lives in a reducer and is reset each time the tour opens. Completion is recorded by the caller via onClose.
 */
export function Tour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [{ step }, dispatch] = useReducer((s: { step: number }, a: 'next' | 'back' | 'reset') => tourReducer(s, a), { step: 0 });
  const total = TOUR_STEPS.length;
  const last = step === total - 1;
  const current = TOUR_STEPS[step];

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) {
      dispatch('reset');
      if (typeof el.showModal === 'function') el.showModal();
      else el.setAttribute('open', '');
      el.querySelector<HTMLButtonElement>('[data-tour-next]')?.focus();
    }
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={overlay.dialog}
      aria-labelledby={titleId}
      data-tour
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
    >
      <div className={overlay.dialogBody}>
        <div className={overlay.dialogHead}>
          <h2 id={titleId}>{current.title}</h2>
          <button type="button" className={overlay.close} onClick={onClose} aria-label="Close tour">
            ×
          </button>
        </div>
        <p className={styles.body} aria-live="polite">
          {current.body}
        </p>
        <div className={styles.footer}>
          <span className={styles.dots}>
            <span className="sr-only">{`Step ${step + 1} of ${total}`}</span>
            <span aria-hidden="true" style={{ display: 'inline-flex', gap: 'var(--space-2)', alignItems: 'center' }}>
              {TOUR_STEPS.map((s, i) => (
                <span key={s.title} className={`${styles.dot} ${i === step ? styles.dotOn : ''}`} />
              ))}
            </span>
            <span aria-hidden="true" style={{ marginLeft: 'var(--space-2)', fontSize: 'var(--text-sm)', color: 'var(--text-muted)' }}>
              Step {step + 1} of {total}
            </span>
          </span>
          <span className={styles.buttons}>
            {!last && (
              <Button variant="ghost" size="sm" onClick={onClose}>
                Skip
              </Button>
            )}
            {step > 0 && (
              <Button variant="secondary" size="sm" onClick={() => dispatch('back')}>
                Back
              </Button>
            )}
            <Button data-tour-next size="sm" onClick={() => (last ? onClose() : dispatch('next'))}>
              {last ? 'Done' : 'Next'}
            </Button>
          </span>
        </div>
      </div>
    </dialog>
  );
}
