'use client';

import React, { useCallback, useEffect, useRef } from 'react';
import { LinkButton } from '../../components/ds';
import { homeCopy as c } from './copy';
import { curvePoints, INTERVENTION_X, revealX, scrollProgress } from './curve';
import styles from './CounterfactualHero.module.css';

const POINTS = curvePoints(80);

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || 'currentColor';
}

function draw(canvas: HTMLCanvasElement, progress: number) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const dpr = window.devicePixelRatio || 1;
  const { width, height } = canvas.getBoundingClientRect();
  if (!width || !height) return;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const pad = 24;
  const px = (x: number) => pad + x * (width - 2 * pad);
  const py = (y: number) => height - pad - y * (height - 2 * pad);
  const reveal = revealX(progress);

  ctx.strokeStyle = cssVar('--border-default');
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad, height - pad);
  ctx.lineTo(width - pad, height - pad);
  ctx.stroke();

  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(px(INTERVENTION_X), pad);
  ctx.lineTo(px(INTERVENTION_X), height - pad);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = cssVar('--text-muted');
  ctx.font = '12px sans-serif';
  ctx.fillText(c.legendIntervention, px(INTERVENTION_X) + 6, pad + 10);

  const visible = POINTS.filter((p) => p.x <= reveal);
  const line = (key: 'observed' | 'twin', color: string, w: number) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = w;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    visible.forEach((p, i) => (i ? ctx.lineTo(px(p.x), py(p[key])) : ctx.moveTo(px(p.x), py(p[key]))));
    ctx.stroke();
  };
  line('twin', cssVar('--series-synthetic'), 2.5);
  line('observed', cssVar('--series-observed'), 3);
}

export function CounterfactualHero() {
  const sectionRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const progress = useRef(1);
  const figureRef = useRef<HTMLElement>(null);
  const frame = useRef(0);

  const render = useCallback(() => {
    frame.current = 0;
    if (canvasRef.current) draw(canvasRef.current, progress.current);
  }, []);
  const schedule = useCallback(() => {
    if (frame.current) return;
    frame.current = requestAnimationFrame(render);
    // Throttled or hidden tabs may never deliver a frame: draw directly so the hero is never blank.
    window.setTimeout(() => {
      if (frame.current) {
        cancelAnimationFrame(frame.current);
        render();
      }
    }, 120);
  }, [render]);

  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
    // Intro: the divergence plays by itself on load, so the first screen already shows the idea.
    // Scrolling can only move it further along, never back.
    const INTRO_MS = 2600;
    const introStart = Date.now();
    let intro = 0;
    const update = () => {
      const el = sectionRef.current;
      if (reduce.matches || !el) progress.current = 1;
      else {
        const r = el.getBoundingClientRect();
        progress.current = Math.max(scrollProgress(r.top, r.height, window.innerHeight), intro);
      }
      if (figureRef.current) figureRef.current.style.transform = reduce.matches ? '' : `translateY(${(progress.current * -18).toFixed(1)}px)`;
      schedule();
    };
    update();
    const introTimer = window.setInterval(() => {
      const t = Math.min((Date.now() - introStart) / INTRO_MS, 1);
      intro = 1 - (1 - t) ** 3;
      update();
      if (t >= 1) window.clearInterval(introTimer);
    }, 50);
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    reduce.addEventListener('change', update);
    const mo = new MutationObserver(schedule);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    const dark = window.matchMedia('(prefers-color-scheme: dark)');
    dark.addEventListener('change', schedule);
    return () => {
      window.clearInterval(introTimer);
      window.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
      reduce.removeEventListener('change', update);
      dark.removeEventListener('change', schedule);
      mo.disconnect();
      cancelAnimationFrame(frame.current);
    };
  }, [schedule]);

  return (
    <section ref={sectionRef} className={styles.section} aria-labelledby="hero-title">
      <div className={`gt-container ${styles.sticky}`}>
        <div className={styles.copy}>
          <h1 id="hero-title">{c.headline}</h1>
          <p className={styles.promise}>{c.promise}</p>
          <div className={styles.actions}>
            <LinkButton href="/app" size="lg">{c.primary}</LinkButton>
            <LinkButton href="/method" variant="secondary" size="lg">{c.secondary}</LinkButton>
          </div>
        </div>
        <figure ref={figureRef} className={styles.figure}>
          <canvas ref={canvasRef} className={styles.canvas} role="img" aria-label={c.heroAlt} />
          <figcaption className={styles.caption}>
            <span className={styles.badge}>{c.illustrative}</span>
            <span className={styles.key}><i className={styles.swObs} />{c.legendObserved}</span>
            <span className={styles.key}><i className={styles.swTwin} />{c.legendTwin}</span>
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
