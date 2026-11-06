'use client';

import React, { useState } from 'react';
import { Dialog } from '../ds/Overlay';
import { Button } from '../ds/Button';
import styles from './Tour.module.css';

export const TOUR_STORAGE_KEY = 'gt-tour-seen';

const STEPS = [
  { title: 'Welcome to GroundTruth', body: 'We estimate what a restoration or carbon project actually achieved by comparing it with a blended “twin” built from similar land that was left alone.' },
  { title: 'Simulated data, always labelled', body: 'Everything you see today runs on a simulated test fixture. The violet “Simulated data” chip stays on screen to remind you that no real project has been analysed.' },
  { title: 'Choose how much detail you want', body: 'Story keeps it plain. Explorer adds interactive evidence. Auditor shows every diagnostic and the full provenance. Switch any time from the top bar.' },
  { title: 'Move fast', body: 'Press Ctrl/⌘ K to jump anywhere, or try typing “compare kariba and mikoko”. Press ? for every shortcut.' },
] as const;

export function Tour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [step, setStep] = useState(0);
  const last = step === STEPS.length - 1;
  const finish = () => {
    try {
      window.localStorage.setItem(TOUR_STORAGE_KEY, '1');
    } catch {
      /* will simply show again */
    }
    setStep(0);
    onClose();
  };
  return (
    <Dialog open={open} onClose={finish} title={STEPS[step].title}>
      <p className={styles.body}>{STEPS[step].body}</p>
      <div className={styles.footer}>
        <span className={styles.dots} aria-label={`Step ${step + 1} of ${STEPS.length}`}>
          {STEPS.map((_, i) => (
            <span key={i} className={`${styles.dot} ${i === step ? styles.dotOn : ''}`} />
          ))}
        </span>
        <span className={styles.buttons}>
          <Button variant="ghost" size="sm" onClick={finish}>
            Skip
          </Button>
          <Button size="sm" onClick={() => (last ? finish() : setStep(step + 1))}>
            {last ? 'Get started' : 'Next'}
          </Button>
        </span>
      </div>
    </Dialog>
  );
}
