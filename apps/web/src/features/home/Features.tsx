import React from 'react';
import { FileCheck2, FlaskConical, Repeat, ScrollText, ShieldAlert, Table2 } from 'lucide-react';
import { Reveal } from '../../components/ds';
import { featureList } from './data';
import styles from './Landing.module.css';

const icons = { FileCheck2, FlaskConical, Repeat, ScrollText, ShieldAlert, Table2 };

export function Features() {
  return (
    <section className={`gt-container ${styles.section}`} aria-labelledby="features-title">
      <Reveal><h2 id="features-title">What you get</h2></Reveal>
      <ul className={styles.grid}>
        {featureList.map((f, i) => {
          const Icon = icons[f.icon];
          return (
            <Reveal as="li" key={f.id} delay={(i % 3) * 80}>
              <article className={styles.feature}>
                <span className={styles.icon}><Icon size={22} aria-hidden="true" /></span>
                <h3>{f.title}</h3>
                <p>{f.body}</p>
              </article>
            </Reveal>
          );
        })}
      </ul>
    </section>
  );
}
