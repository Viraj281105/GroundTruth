// Records the GroundTruth demonstration by driving the real app in Chrome at 1920x1080.
//
// Narration drives the pacing: every sentence is a "beat". A beat starts an on-screen action and
// holds for the sentence's rendered audio duration, and the start time of every beat is written to
// cues.json, so audio and subtitles are aligned to what is on screen by construction.
//
// Capture is Chrome DevTools screencast (JPEG frames with timestamps); assemble.py turns the frames,
// cues and narration WAVs into the final MP4. No screen-recorder, no network service.
//
//   FAST=1 node record.mjs   rehearsal: same actions, ~no waiting, no capture (finds broken steps)
//   node record.mjs          real take
//
// Environment: AUDIT_PASSWORDS_FILE (demo seed credentials), VIDEO_OUT (work directory holding
// wav/ and durations.json from tts.ps1), AUDIT_BASE_URL (default http://localhost:3100).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { base, credentials } from '../lib.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const FAST = process.env.FAST === '1';
const OUT = path.resolve(process.env.VIDEO_OUT ?? 'video-out');
const FRAMES = path.join(OUT, 'frames');
const SLUG = 'sahyadri-foothills-restoration-demonstration';
const SIZE = { width: 1920, height: 1080 };
const GAP = FAST ? 0.05 : 0.4; // breathing room after each sentence

const narration = JSON.parse(fs.readFileSync(path.join(here, 'narration.json'), 'utf8'));
const durations = JSON.parse(fs.readFileSync(path.join(OUT, 'durations.json'), 'utf8'));
const text = Object.fromEntries(narration.scenes.flatMap((s) => s.sentences.map((t, i) => [`${s.id}-${i + 1}`, t])));
const dur = (id) => (FAST ? 0.3 : durations[id]);
if (!FAST) {
  fs.rmSync(FRAMES, { recursive: true, force: true });
  fs.mkdirSync(FRAMES, { recursive: true });
}

const wall = () => Date.now() / 1000;
const sleep = (s) => new Promise((r) => setTimeout(r, s * 1000));
const creds = credentials();
const log = (m) => console.log(`[record ${new Date().toISOString().slice(11, 19)}] ${m}`);

const browser = await chromium.launch({ channel: process.env.AUDIT_CHANNEL ?? 'chrome' });
const context = await browser.newContext({ viewport: SIZE, deviceScaleFactor: 1, acceptDownloads: true });

// --- overlays injected into every document: a visible cursor, and the scene title card ----------
await context.addInitScript(() => {
  const css = `
    #gt-cursor{position:fixed;z-index:2147483646;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;
      border:2px solid #fff;background:rgba(20,120,80,.55);box-shadow:0 0 0 1.5px rgba(0,0,0,.45);pointer-events:none;
      transition:transform .12s ease, background .12s ease;left:-50px;top:-50px}
    #gt-cursor.down{transform:scale(.7);background:rgba(250,180,40,.8)}
    #gt-card{position:fixed;inset:0;z-index:2147483647;background:#10231b;color:#f3f1ea;display:flex;flex-direction:column;
      align-items:center;justify-content:center;text-align:center;padding:0 160px;opacity:0;transition:opacity .45s ease;
      font-family:Georgia,'Times New Roman',serif}
    #gt-card.on{opacity:1}
    #gt-card:not(.on){pointer-events:none}
    #gt-card .k{font:600 22px/1 Consolas,monospace;letter-spacing:.35em;color:#7fd1a8;margin-bottom:34px}
    #gt-card h1{font-size:68px;line-height:1.15;font-weight:500;margin:0 0 26px;max-width:1500px}
    #gt-card p{font:400 30px/1.5 'Segoe UI',system-ui,sans-serif;color:#c9d6cf;margin:0;max-width:1400px}
    #gt-card ul{font:400 30px/1.7 'Segoe UI',system-ui,sans-serif;color:#dfe8e2;text-align:left;margin:34px 0 0;padding-left:34px}`;
  const mountCursor = () => {
    if (document.getElementById('gt-cursor') || !document.documentElement) return;
    const style = document.createElement('style');
    style.textContent = css;
    document.documentElement.appendChild(style);
    const c = document.createElement('div');
    c.id = 'gt-cursor';
    document.documentElement.appendChild(c);
    window.addEventListener('mousemove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    window.addEventListener('mousedown', () => c.classList.add('down'), true);
    window.addEventListener('mouseup', () => c.classList.remove('down'), true);
  };
  const build = (card) => {
    const el = document.createElement('div');
    el.id = 'gt-card';
    const esc = (s) => String(s).replace(/[&<>]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[ch]);
    el.innerHTML = `<div class="k">GROUNDTRUTH</div><h1>${esc(card.title)}</h1>` +
      (card.sub ? `<p>${esc(card.sub)}</p>` : '') +
      (card.items ? `<ul>${card.items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : '');
    return el;
  };
  window.__gtShowCard = (card, instant) => {
    mountCursor();
    document.getElementById('gt-card')?.remove();
    const el = build(card);
    if (instant) el.style.transition = 'none';
    document.documentElement.appendChild(el);
    requestAnimationFrame(() => el.classList.add('on'));
  };
  window.__gtHideCard = () => {
    const el = document.getElementById('gt-card');
    if (el) { el.classList.remove('on'); setTimeout(() => el.remove(), 600); }
    try { sessionStorage.removeItem('gtCard'); } catch { /* ignore */ }
  };
  // Keep the card up across navigations while a scene is being set up behind it.
  const restore = () => {
    mountCursor();
    let raw = null;
    try { raw = sessionStorage.getItem('gtCard'); } catch { /* ignore */ }
    if (raw && document.documentElement && !document.getElementById('gt-card')) window.__gtShowCard(JSON.parse(raw), true);
  };
  new MutationObserver(restore).observe(document, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', restore);
  restore();
});

const page = await context.newPage();
const cues = [];

// --- helpers --------------------------------------------------------------------------------------
async function showCard(card) {
  await page.evaluate((c) => { try { sessionStorage.setItem('gtCard', JSON.stringify(c)); } catch { /* ignore */ } window.__gtShowCard(c); }, card);
  await sleep(FAST ? 0.1 : 0.7);
}
async function hideCard() {
  await page.evaluate(() => window.__gtHideCard());
  await sleep(FAST ? 0.1 : 0.7);
}
async function settle(extra = 0.5) {
  await page.waitForLoadState('domcontentloaded').catch(() => {});
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
  await sleep(FAST ? 0.1 : extra);
}
const glide = (y, seconds) =>
  page
    .evaluate(
      ({ y, ms }) =>
        new Promise((resolve) => {
          const start = window.scrollY, delta = Math.max(0, Math.min(y, document.documentElement.scrollHeight - innerHeight)) - start;
          const t0 = performance.now();
          const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
          const step = (now) => {
            const p = Math.min(1, (now - t0) / Math.max(ms, 1));
            window.scrollTo(0, start + delta * ease(p));
            p < 1 ? requestAnimationFrame(step) : resolve();
          };
          requestAnimationFrame(step);
        }),
      { y, ms: seconds * 1000 },
    )
    .catch(() => {});
async function glideTo(locator, seconds, offset = 90) {
  const y = await locator.first().evaluate((el, o) => el.getBoundingClientRect().top + window.scrollY - o, offset).catch(() => null);
  if (y !== null) await glide(y, seconds);
}
async function glideDialog(seconds, fraction) {
  await page
    .evaluate(
      ({ ms, fraction }) =>
        new Promise((resolve) => {
          const d = document.querySelector('dialog[open]');
          const nodes = d ? [d, ...d.querySelectorAll('*')] : [];
          const el = nodes.find((n) => n.scrollHeight > n.clientHeight + 20 && /auto|scroll/.test(getComputedStyle(n).overflowY));
          if (!el) return resolve();
          const start = el.scrollTop, target = (el.scrollHeight - el.clientHeight) * fraction, t0 = performance.now();
          const step = (now) => {
            const p = Math.min(1, (now - t0) / Math.max(ms, 1));
            el.scrollTop = start + (target - start) * p;
            p < 1 ? requestAnimationFrame(step) : resolve();
          };
          requestAnimationFrame(step);
        }),
      { ms: seconds * 1000, fraction },
    )
    .catch(() => {});
}
async function moveTo(locator, steps = 28) {
  const el = locator.first();
  await el.scrollIntoViewIfNeeded().catch(() => {});
  const box = await el.boundingBox();
  if (!box) return;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: FAST ? 2 : steps });
}
async function clickOn(locator) {
  await moveTo(locator);
  await sleep(FAST ? 0.02 : 0.35);
  await locator.first().click();
}
async function type(locator, value, delay = 75) {
  await clickOn(locator);
  await locator.first().pressSequentially(value, { delay: FAST ? 0 : delay });
}

/** One narrated sentence: start its action now, then hold until the audio has finished. */
async function beat(id, action = async () => {}) {
  const start = wall();
  cues.push({ id, start, dur: durations[id], text: text[id] });
  log(`${id} (${dur(id).toFixed(1)}s)`);
  await Promise.all([action(dur(id)), sleep(dur(id) + GAP)]);
}

/** A scene: title card up, set up behind it, card down, then the narrated beats. */
async function scene(card, setup, body, { keepCard = false } = {}) {
  const shown = wall();
  await showCard(card);
  await setup();
  await settle(0.3);
  await sleep(Math.max(0, (FAST ? 0.2 : 1.7) - (wall() - shown)));
  if (!keepCard) await hideCard();
  await body();
}

const main = page.locator('main');
const nav = page.getByRole('navigation', { name: 'Main', exact: true });
const projectUrl = (org, tab) => `${base}/app/${org}/projects/${SLUG}/${tab}`;
const signInForm = async (email, { slow = false } = {}) => {
  await page.goto(`${base}/login`);
  await settle(0.2);
  const emailBox = page.getByLabel('Email');
  const passBox = page.getByLabel('Password', { exact: true });
  if (slow) {
    await type(emailBox, email);
    await type(passBox, creds[email], 60);
    await clickOn(page.getByRole('button', { name: 'Sign in' }));
  } else {
    await emailBox.fill(email);
    await passBox.fill(creds[email]);
    await passBox.press('Enter'); // the title card is covering the button during scene setup
  }
  await page.waitForURL(/\/app\//, { timeout: 20000 });
  await settle(0.3);
};

// --- start: title card on the landing page, then begin capture -----------------------------------
await context.clearCookies();
await page.goto(`${base}/`);
await settle(0.3);
// The welcome tour opens on a first visit and, as a modal dialog, would sit above the title card.
// Dismiss it before capture starts.
await sleep(FAST ? 0.2 : 2.0);
{
  const skip = page.getByRole('button', { name: 'Skip', exact: true });
  if (await skip.isVisible().catch(() => false)) await skip.evaluate((el) => el.click());
  await sleep(0.3);
}
await page.evaluate(() => window.__gtShowCard({ title: 'GroundTruth', sub: 'What a restoration project claims, against what can be observed' }, true));
await page.evaluate(() => { try { sessionStorage.setItem('gtCard', JSON.stringify({ title: 'GroundTruth', sub: 'What a restoration project claims, against what can be observed' })); } catch { /* ignore */ } });

const frames = [];
let cdp = null;
let skew = [];
if (!FAST) {
  cdp = await context.newCDPSession(page);
  cdp.on('Page.screencastFrame', (f) => {
    const file = path.join(FRAMES, `f${String(frames.length).padStart(6, '0')}.jpg`);
    fs.writeFileSync(file, Buffer.from(f.data, 'base64'));
    if (skew.length < 20) skew.push(wall() - f.metadata.timestamp);
    frames.push({ file, t: f.metadata.timestamp });
    cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {});
  });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 88, maxWidth: SIZE.width, maxHeight: SIZE.height, everyNthFrame: 1 });
}
await sleep(FAST ? 0.1 : 2.6);

// --- scene 0: the problem (public landing page) ---------------------------------------------------
await scene({ title: 'The accountability problem', sub: 'Claims are easy to make and hard to check' }, async () => {
  await page.goto(`${base}/`);
  // A first visit opens the welcome tour over the page. Dismiss it behind the card, as a user would.
  await sleep(FAST ? 0.2 : 1.6);
  const skip = page.getByRole('button', { name: 'Skip', exact: true });
  if (await skip.isVisible().catch(() => false)) await skip.evaluate((el) => el.click());
}, async () => {
  const total = async () => (await page.evaluate(() => document.documentElement.scrollHeight - innerHeight)) || 0;
  const t = await total();
  for (let i = 1; i <= 5; i++) await beat(`s0-${i}`, (d) => glide((t * i) / 5, d * 0.85));
});

// --- scene 1: the NGO signs in and opens its project ---------------------------------------------
await scene({ title: 'The NGO', sub: 'Sign in, open a project' }, async () => {
  await context.clearCookies();
  await page.goto(`${base}/login`);
}, async () => {
  const email = 'ngo@demo.groundtruth.local';
  await beat('s1-1', async () => {
    await signInForm(email, { slow: true });
  });
  await beat('s1-2', async (d) => {
    await sleep(FAST ? 0 : Math.min(2.5, d * 0.25)); // the welcome tour is on screen first
    const skip = page.getByRole('button', { name: 'Skip', exact: true });
    if (await skip.isVisible().catch(() => false)) await clickOn(skip);
    await glide(420, d * 0.5);
  });
  await beat('s1-3', async (d) => {
    await glide(0, 0.6);
    await clickOn(nav.getByRole('link', { name: 'Projects', exact: true }));
    await settle(0.4);
    await clickOn(main.getByRole('link', { name: /Sahyadri Foothills/ }));
    await settle(0.8);
  });
  await beat('s1-4', async (d) => {
    await moveTo(main.getByText('PROJECT PROGRESS', { exact: false }));
    await glide(0, 0.6);
  });
});

// --- scene 2: boundary, documents, claim extraction ----------------------------------------------
await scene({ title: 'Boundary, documents and claims', sub: 'What the project says about itself' }, async () => {
  // The boundary map is on the NGO dashboard, for the selected project.
  await page.goto(`${base}/app/demo-ngo/dashboard?project=${SLUG}`);
  await settle(2.5); // map tiles
}, async () => {
  await beat('s2-1', async (d) => {
    const map = page.getByRole('heading', { name: /Project area and comparison areas/i });
    await glideTo(map, Math.min(2.5, d * 0.4), 110);
    await sleep(FAST ? 0 : 0.4);
    await moveTo(page.locator('canvas').first());
  });
  await beat('s2-2', async (d) => {
    await glide(0, 0.5);
    await clickOn(nav.getByRole('link', { name: 'Projects', exact: true }));
    await settle(0.3);
    await clickOn(main.getByRole('link', { name: /Sahyadri Foothills/ }));
    await settle(0.5);
    await clickOn(main.getByRole('link', { name: 'Evidence', exact: true }));
    await settle(0.5);
    await glideTo(page.getByRole('heading', { name: /Project documents/i }), Math.max(1, d * 0.3), 110);
  });
  await beat('s2-3', async (d) => {
    await sleep(FAST ? 0 : 0.8);
    await clickOn(main.getByRole('button', { name: /View extracted statements/i }));
    await settle(1.0);
  });
  await beat('s2-4', async (d) => {
    await glideDialog(d * 0.9, 0.45);
  });
  await beat('s2-5', async (d) => {
    await glideDialog(d * 0.7, 1);
  });
});

// --- scene 3: real satellite observations ---------------------------------------------------------
await scene({ title: 'Real satellite observations', sub: 'Sentinel-2, derived indicators, scene by scene' }, async () => {
  await page.keyboard.press('Escape');
  await page.goto(projectUrl('demo-ngo', 'observation'));
}, async () => {
  await beat('s3-1', async (d) => {
    await glideTo(page.getByRole('heading', { name: /Request satellite data/i }), 0.5, 100);
    await moveTo(page.getByText('Which years?').first());
    await glide(260, d * 0.7);
  });
  await beat('s3-2', async (d) => {
    await glideTo(page.getByRole('heading', { name: /Your requests/i }), d * 0.6, 100);
  });
  await beat('s3-3', async (d) => {
    await glideTo(page.getByRole('heading', { name: /Vegetation index series/i }), d * 0.35, 90);
    await sleep(FAST ? 0 : d * 0.25);
    await clickOn(main.getByRole('button', { name: 'EVI', exact: true }));
    await sleep(FAST ? 0 : 1.0);
    await clickOn(main.getByRole('button', { name: 'NDVI', exact: true }));
  });
  await beat('s3-4', async (d) => {
    await clickOn(main.getByRole('button', { name: 'Table', exact: true }));
    await sleep(FAST ? 0 : 0.5);
    await glideTo(main.getByRole('columnheader', { name: /Scene ids/i }), d * 0.7, 300);
  });
  await beat('s3-5', async (d) => {
    await moveTo(main.getByRole('columnheader', { name: /Evidence state/i }));
  });
  await beat('s3-6', async (d) => {
    await clickOn(main.getByRole('button', { name: 'Chart', exact: true }));
    await sleep(FAST ? 0 : 0.5);
    await glideTo(page.getByRole('heading', { name: /Vegetation index series/i }), 0.8, 90);
  });
});

// --- scene 4: claim assessment --------------------------------------------------------------------
await scene({ title: 'Claim assessment', sub: 'Each claim is judged on its own evidence' }, async () => {
  await page.goto(projectUrl('demo-ngo', 'verification'));
}, async () => {
  const at = (re) => page.getByText(re).first();
  await beat('s4-1', async () => {
    await glide(0, 0.5);
  });
  await beat('s4-2', async (d) => {
    await glideTo(at(/area restored/i), d * 0.6, 150);
  });
  await beat('s4-3', async (d) => {
    await glideTo(at(/vegetation improvement/i), d * 0.6, 150);
  });
  await beat('s4-4', async (d) => {
    await glideTo(at(/tree survival/i), d * 0.35, 150);
    await glideTo(at(/biodiversity improvement/i), d * 0.55, 400);
  });
  await beat('s4-5', async (d) => {
    await glideTo(at(/Attribution readiness/i), d * 0.7, 120);
  });
});

// --- scene 5: dossier, provenance, ledger ---------------------------------------------------------
const dossierPath = path.join(OUT, 'dossier.zip');
await scene({ title: 'Evidence dossier and audit ledger', sub: 'Provenance an auditor can check' }, async () => {
  await page.goto(projectUrl('demo-ngo', 'reports'));
}, async () => {
  const dl = main.getByRole('button', { name: /Download dossier/i });
  await beat('s5-1', async () => {
    await moveTo(dl);
  });
  await beat('s5-2', async () => {
    const [download] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), clickOn(dl)]);
    await download.saveAs(dossierPath);
    await main.getByText(/now sealed in the audit ledger/i).waitFor({ timeout: 15000 });
  });
  await beat('s5-3', async (d) => {
    await glideTo(page.getByRole('heading', { name: /Audit ledger/i }), d * 0.6, 100);
  });
  await beat('s5-4', async (d) => {
    await glideTo(main.getByText(/Report sealed/i).last(), d * 0.6, 420);
  });
  await beat('s5-5', async () => {
    await moveTo(main.getByText(/Ledger verified/i));
  });
});

// --- scene 6: funder, auditor, roadmap ------------------------------------------------------------
await scene({ title: 'The funder', sub: 'View access: read, but not change' }, async () => {
  await context.clearCookies();
  await signInForm('funder@demo.groundtruth.local');
  await page.goto(projectUrl('demo-funder', 'evidence'));
}, async () => {
  await beat('s6-1', async (d) => {
    await glideTo(page.getByRole('heading', { name: /Project documents/i }), d * 0.25, 110);
    await sleep(FAST ? 0 : d * 0.15);
    await clickOn(main.getByRole('link', { name: 'Reports', exact: true }));
    await settle(0.6);
    await glideTo(page.getByRole('heading', { name: /Audit ledger/i }), d * 0.3, 100);
  });
});

await scene({ title: 'The auditor', sub: 'Audit access: the dossier, and the means to check it' }, async () => {
  await context.clearCookies();
  await signInForm('auditor@demo.groundtruth.local');
  await page.goto(projectUrl('demo-auditor', 'reports'));
}, async () => {
  await beat('s6-2', async (d) => {
    await moveTo(main.getByRole('button', { name: /Download dossier/i }));
    await glideTo(page.getByRole('heading', { name: /Check a downloaded report/i }), d * 0.5, 160);
  });
  await beat('s6-3', async (d) => {
    await moveTo(main.locator('input[type=file]'));
    await main.locator('input[type=file]').setInputFiles(dossierPath);
    await sleep(FAST ? 0 : 0.5);
    await clickOn(main.getByRole('button', { name: 'Check file' }));
    await main.getByText(/byte-identical/i).waitFor({ timeout: 15000 });
  });
});

await scene(
  {
    title: 'What was claimed. What was observed. What cannot yet be shown.',
    items: [
      'Observations from before a project began',
      'Climate and comparison-area data, so attribution becomes possible',
      'Field validation of the satellite values',
    ],
  },
  async () => {},
  async () => {
    await beat('s6-4');
    await beat('s6-5');
    await sleep(FAST ? 0.1 : 3.0);
  },
  { keepCard: true },
);

// --- finish -----------------------------------------------------------------------------------------
const end = wall();
if (!FAST) await cdp.send('Page.stopScreencast');
await context.close();
await browser.close();

if (!FAST) {
  const t0 = frames[0].t;
  const medianSkew = [...skew].sort((a, b) => a - b)[Math.floor(skew.length / 2)];
  fs.writeFileSync(
    path.join(OUT, 'cues.json'),
    JSON.stringify({ clockSkewSeconds: medianSkew, duration: end - medianSkew - t0, cues: cues.map((c) => ({ ...c, start: c.start - medianSkew - t0 })) }, null, 1),
  );
  const lines = [];
  for (let i = 0; i < frames.length; i++) {
    const next = frames[i + 1]?.t ?? end - medianSkew;
    lines.push(`file '${frames[i].file.replace(/\\/g, '/')}'`, `duration ${Math.max(next - frames[i].t, 0.001).toFixed(4)}`);
  }
  lines.push(`file '${frames[frames.length - 1].file.replace(/\\/g, '/')}'`);
  fs.writeFileSync(path.join(OUT, 'frames.txt'), lines.join('\n'));
  log(`frames: ${frames.length}, length: ${(end - medianSkew - t0).toFixed(1)} s, clock skew (wall - frame clock): ${medianSkew.toFixed(3)} s`);
} else {
  log('rehearsal finished without errors');
}
