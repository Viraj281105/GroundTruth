import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it } from 'vitest';
import { Tour } from '../src/components/shell/Tour';
import { TourButton } from '../src/components/shell/TourButton';
import { TOUR_STEPS, TOUR_STORAGE_KEY, hasSeenTour, markTourSeen, resetTourSessionMemory, tourReducer, tourSuppressedOn } from '../src/lib/tour-core';

const memoryStorage = () => {
  const data = new Map<string, string>();
  return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) };
};
const blockedStorage = {
  getItem: () => {
    throw new Error('blocked');
  },
  setItem: () => {
    throw new Error('blocked');
  },
};

beforeEach(() => resetTourSessionMemory());

describe('tour reducer', () => {
  it('advances with Next, goes back with Back and stays inside the steps', () => {
    let s = { step: 0 };
    s = tourReducer(s, 'back');
    expect(s.step).toBe(0);
    for (let i = 1; i < TOUR_STEPS.length; i++) {
      s = tourReducer(s, 'next');
      expect(s.step).toBe(i);
    }
    expect(tourReducer(s, 'next').step).toBe(TOUR_STEPS.length - 1);
    expect(tourReducer(s, 'back').step).toBe(TOUR_STEPS.length - 2);
    expect(tourReducer(s, 'reset').step).toBe(0);
  });

  it('every step has its own title and body, so Next visibly changes the text', () => {
    expect(new Set(TOUR_STEPS.map((s) => s.title)).size).toBe(TOUR_STEPS.length);
    expect(new Set(TOUR_STEPS.map((s) => s.body)).size).toBe(TOUR_STEPS.length);
  });
});

describe('tour persistence', () => {
  it('is unseen until completion is recorded, then stays seen across page loads', () => {
    const storage = memoryStorage();
    expect(hasSeenTour(storage)).toBe(false);
    markTourSeen(storage);
    expect(storage.getItem(TOUR_STORAGE_KEY)).toBe('1');
    resetTourSessionMemory(); // simulates a full reload: only localStorage remains
    expect(hasSeenTour(storage)).toBe(true);
  });

  it('falls back to session memory when storage is blocked, so it does not reappear on every navigation', () => {
    expect(hasSeenTour(blockedStorage)).toBe(false);
    expect(() => markTourSeen(blockedStorage)).not.toThrow();
    expect(hasSeenTour(blockedStorage)).toBe(true);
    expect(hasSeenTour(null)).toBe(true);
  });

  it('works with no storage at all', () => {
    expect(hasSeenTour(null)).toBe(false);
    expect(() => markTourSeen(null)).not.toThrow();
  });

  it('never opens on its own over the sign-in and register forms', () => {
    for (const p of ['/login', '/register', '/sign-in', '/login/']) expect(tourSuppressedOn(p)).toBe(true);
    for (const p of ['/', '/app/demo/dashboard', '/method', '/loginfo']) expect(tourSuppressedOn(p)).toBe(false);
  });
});

describe('Tour markup', () => {
  const html = renderToStaticMarkup(<Tour open={false} onClose={() => undefined} />);

  it('is a labelled dialog showing step X of N with a working control set', () => {
    expect(html).toMatch(/<dialog[^>]*aria-labelledby="([^"]+)"/);
    const id = /aria-labelledby="([^"]+)"/.exec(html)![1];
    expect(html).toContain(`<h2 id="${id}">${TOUR_STEPS[0].title}</h2>`);
    expect(html).toContain(`Step 1 of ${TOUR_STEPS.length}`);
    expect(html).toContain('>Next<');
    expect(html).toContain('>Skip<');
    expect(html).not.toContain('>Back<'); // nothing to go back to on the first step
    expect(html).toContain('aria-label="Close tour"');
  });

  it('offers a way to replay the tour', () => {
    expect(renderToStaticMarkup(<TourButton />)).toContain('Show the tour again');
  });
});
