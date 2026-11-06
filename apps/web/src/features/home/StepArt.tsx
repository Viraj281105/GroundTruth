import React from 'react';
import styles from './StepArt.module.css';

/** Decorative illustrations (the step text carries the meaning), drawn with theme tokens only. */
export function StepArt({ step }: { step: 0 | 1 | 2 }) {
  return (
    <svg className={styles.art} viewBox="0 0 200 90" aria-hidden="true" focusable="false">
      {step === 0 && (
        <g fill="none" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 22 C30 18 42 30 70 34" className={styles.donor} />
          <path d="M6 44 C30 50 44 40 70 42" className={styles.donor} />
          <path d="M6 66 C30 60 44 56 70 50" className={styles.donor} />
          <path d="M6 82 C32 80 46 62 70 56" className={styles.donor} />
          <circle cx="70" cy="34" r="2.200" className={styles.dot} /><circle cx="70" cy="42" r="2.200" className={styles.dot} />
          <circle cx="70" cy="50" r="2.200" className={styles.dot} /><circle cx="70" cy="56" r="2.200" className={styles.dot} />
          <path d="M72 45 H110" className={styles.flow} />
          <path d="M110 45 l-5 -4 M110 45 l-5 4" className={styles.flow} />
          <path d="M118 62 C140 52 150 50 172 36 L194 28" className={styles.twin} />
        </g>
      )}
      {step === 1 && (
        <g fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M100 6 V84" className={styles.marker} />
          <path d="M8 56 L40 50 L72 54 L100 46 L132 36 L164 26 L194 18" className={styles.obs} />
          <path d="M8 56 L40 51 L72 54 L100 47 L132 50 L164 46 L194 44" className={styles.twin} />
          <path d="M194 18 V44" className={styles.gap} />
        </g>
      )}
      {step === 2 && (
        <g>
          {[10, 18, 30, 46, 56, 44, 30, 20, 12, 6].map((h, i) => (
            <rect key={i} x={10 + i * 14} y={84 - h} width="11" height={h} rx="2" className={styles.bar} />
          ))}
          <rect x="164" y="30" width="11" height="54" rx="2" className={styles.hit} />
          <path d="M169.500 22 V28" className={styles.markerSolid} />
        </g>
      )}
    </svg>
  );
}
