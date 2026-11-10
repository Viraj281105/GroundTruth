// Disposable recording test: proves this machine can capture the app at 1920x1080.
// Capture is by Chrome DevTools screencast frames (JPEG, timestamped), assembled by the system
// ffmpeg. Playwright's built-in recordVideo was not used: it needs Playwright's own ffmpeg
// build, which is not installed here, and this route needs no download.
//
//   node e2e/demo/video/preflight.mjs <outDir>
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const out = path.resolve(process.argv[2] ?? 'preflight-out');
fs.mkdirSync(path.join(out, 'frames'), { recursive: true });
const base = process.env.AUDIT_BASE_URL ?? 'http://localhost:3100';
const size = { width: 1920, height: 1080 };

const browser = await chromium.launch({ channel: process.env.AUDIT_CHANNEL ?? 'chrome' });
const context = await browser.newContext({ viewport: size, deviceScaleFactor: 1 });
const page = await context.newPage();

// B: screencast frames with their timestamps
const cdp = await context.newCDPSession(page);
const frames = [];
cdp.on('Page.screencastFrame', async (f) => {
  const file = path.join(out, 'frames', `f${String(frames.length).padStart(5, '0')}.jpg`);
  frames.push({ file, t: f.metadata.timestamp });
  fs.writeFileSync(file, Buffer.from(f.data, 'base64'));
  await cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {});
});
await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: size.width, maxHeight: size.height, everyNthFrame: 1 });

await page.goto(`${base}/login`);
await page.waitForTimeout(1200);
await page.getByLabel('Email').pressSequentially('someone@example.org', { delay: 60 });
await page.waitForTimeout(600);
await page.goto(`${base}/method`);
await page.waitForTimeout(800);
await page.mouse.wheel(0, 500);
await page.waitForTimeout(1500);

await cdp.send('Page.stopScreencast');
await context.close();
await browser.close();

// ffmpeg concat list with real frame durations
const lines = [];
for (let i = 0; i < frames.length; i++) {
  const next = frames[i + 1]?.t ?? frames[i].t + 0.5;
  lines.push(`file '${frames[i].file.replace(/\\/g, '/')}'`, `duration ${Math.max(next - frames[i].t, 0.001).toFixed(4)}`);
}
if (frames.length) lines.push(`file '${frames[frames.length - 1].file.replace(/\\/g, '/')}'`);
fs.writeFileSync(path.join(out, 'frames.txt'), lines.join('\n'));
console.log(JSON.stringify({ frames: frames.length, seconds: frames.length ? +(frames[frames.length - 1].t - frames[0].t).toFixed(2) : 0 }));
