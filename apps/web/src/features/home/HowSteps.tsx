import React from 'react';
import { Reveal } from '../../components/ds';
import styles from './Landing.module.css';

const donors: [number, number][] = [[30, 40], [70, 90], [40, 150], [90, 200], [110, 60], [130, 130]];
const hist = [10, 22, 40, 62, 80, 62, 42, 24, 12, 6];

function Art({ step }: { step: 0 | 1 | 2 }) {
  const label = ['Scattered donor land areas feeding one synthetic twin line.', 'Project and twin lines diverge after an intervention marker.', 'A histogram of placebo effects with the observed effect far on the right.'][step];
  return (
    <svg className={styles.svg} viewBox="0 0 400 240" role="img" aria-label={label}>
      {step === 0 && (
        <g>
          {donors.map(([x, y], i) => (
            <g key={i}>
              <path className={`${styles.link} ${styles.draw}`} pathLength={1} d={`M${x} ${y} C200 ${y} 220 120 290 120`} />
              <circle className={styles.dotDonor} cx={x} cy={y} r="8" />
            </g>
          ))}
          <path className={`${styles.twin} ${styles.draw}`} pathLength={1} d="M270 150 C300 140 320 110 380 80" />
          <text className={styles.label} x="20" y="230">Similar untouched land</text>
          <text className={styles.label} x="270" y="170">Synthetic twin</text>
        </g>
      )}
      {step === 1 && (
        <g>
          <line className={styles.marker} x1="170" y1="20" x2="170" y2="210" />
          <path className={styles.axis} d="M20 220 H380" />
          <path className={`${styles.twin} ${styles.draw}`} pathLength={1} d="M20 150 L100 146 L170 140 L270 160 L380 170" />
          <path className={`${styles.obs} ${styles.draw}`} pathLength={1} d="M20 150 L100 146 L170 140 L270 100 L380 60" />
          <text className={styles.label} x="176" y="34">Intervention</text>
          <text className={styles.label} x="40" y="180">Paths match before</text>
          <text className={styles.label} x="250" y="200">Gap after</text>
        </g>
      )}
      {step === 2 && (
        <g>
          <path className={styles.axis} d="M20 220 H380" />
          {hist.map((h, i) => (
            <rect key={i} className={`${styles.bar} ${styles.grow}`} style={{ '--i': i } as React.CSSProperties} x={30 + i * 28} y={220 - h * 2} width="22" height={h * 2} rx="3" />
          ))}
          <rect className={`${styles.hit} ${styles.grow}`} style={{ '--i': 10 } as React.CSSProperties} x="330" y="150" width="22" height="70" rx="3" />
          <text className={styles.label} x="20" y="238">Placebo effects (nothing happened)</text>
          <text className={styles.label} x="262" y="140">Observed effect</text>
        </g>
      )}
    </svg>
  );
}

const steps = [
  { title: 'Build a twin from similar untouched land', body: 'Find comparable areas the project never touched (the “donor pool”) and blend them into a synthetic twin that behaved like the project area before it started.' },
  { title: 'Compare the project with its twin', body: 'Before the intervention the two lines should match. Afterwards, the gap between them is the estimated effect, reported with its uncertainty.' },
  { title: 'Stress-test the result', body: 'Run the same method where nothing happened (placebo tests) and with parts removed. A real signal should stand out from that background noise. If it does not, the answer is INCONCLUSIVE.' },
];

export function HowSteps() {
  return (
    <section className={`gt-container ${styles.section}`} id="how" aria-labelledby="how-title">
      <h2 id="how-title">How it works</h2>
      <p className={styles.lead}>Three steps turn a claim into an estimate you can inspect.</p>
      {steps.map((s, i) => (
        <div key={s.title} className={`${styles.split} ${styles.step} ${i % 2 ? styles.flip : ''}`}>
          <Reveal variant={i % 2 ? 'right' : 'left'}>
            <span className={styles.num} aria-hidden="true">{i + 1}</span>
            <h3>{s.title}</h3>
            <p>{s.body}</p>
          </Reveal>
          <Reveal variant="scale" delay={120} className={styles.panel}>
            <Art step={i as 0 | 1 | 2} />
            <span className={styles.sim}>Illustration only, not data</span>
          </Reveal>
        </div>
      ))}
    </section>
  );
}
