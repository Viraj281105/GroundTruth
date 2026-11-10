import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { mkdtempSync, openSync, rmSync } from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { migrateAndSeed, REPO_ROOT, venvBin } from './seed';

/**
 * Playwright globalSetup: migrate + seed a temp SQLite DB, start the API and the web app, wait until both
 * answer, and return a teardown that stops every process it started (also when setup fails).
 *   E2E_BASE_URL     web origin (default http://localhost:3000)
 *   E2E_API_URL      API origin (default http://localhost:8000)
 *   E2E_TMP_DIR      parent for the temp dir holding the DB, logs and the passwords file
 *   E2E_EXTERNAL_STACK=1  use a stack you already run (needs GT_DEMO_PASSWORDS_FILE); starts nothing
 *   E2E_SKIP_BUILD=1      reuse the existing apps/web/.next build
 *   E2E_WORKER_PAUSE_S    seconds each job waits before its engine starts (default 6), so a test can
 *                         cancel a running job; a testing aid the worker refuses in production
 */
const WEB = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const API = process.env.E2E_API_URL ?? 'http://localhost:8000';
const WEB_DIR = path.resolve(__dirname, '..');
const isWin = process.platform === 'win32';

const children: ChildProcess[] = [];

function killTree(child: ChildProcess): void {
  if (child.pid === undefined) return;
  if (isWin) spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F']);
  else child.kill('SIGTERM');
}

function stopAll(): void {
  for (const c of children.splice(0)) killTree(c);
}

function portFree(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const probe = net.createServer();
    probe.once('error', () => resolve(false));
    probe.listen(port, '127.0.0.1', () => probe.close(() => resolve(true)));
  });
}

async function waitFor(url: string, label: string, ms: number): Promise<void> {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      const res = await fetch(url);
      if (res.status < 500) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`${label} did not answer at ${url} within ${ms / 1000}s`);
}

function start(cmd: string, args: string[], cwd: string, env: NodeJS.ProcessEnv, log: string, shell = false): void {
  const fd = openSync(log, 'a');
  children.push(spawn(cmd, args, { cwd, env, stdio: ['ignore', fd, fd], shell, windowsHide: true }));
}

function runSync(cmd: string, args: string[], cwd: string, env: NodeJS.ProcessEnv): void {
  const res = spawnSync(cmd, args, { cwd, env, encoding: 'utf8', shell: isWin });
  if (res.status !== 0) throw new Error(`${cmd} ${args.join(' ')} failed:\n${(res.stdout + res.stderr).slice(-2000)}`);
}

export default async function globalSetup(): Promise<() => Promise<void>> {
  if (process.env.E2E_EXTERNAL_STACK === '1') return async () => {};

  const apiPort = Number(new URL(API).port || 80);
  const webPort = Number(new URL(WEB).port || 80);
  for (const [port, name] of [[apiPort, 'API'], [webPort, 'web']] as const) {
    if (!(await portFree(port))) {
      throw new Error(`port ${port} (${name}) is already in use; set E2E_BASE_URL / E2E_API_URL to free ports`);
    }
  }

  const tmp = mkdtempSync(path.join(process.env.E2E_TMP_DIR ?? os.tmpdir(), 'gt-e2e-'));
  const passwords = path.join(tmp, 'demo-passwords.tsv');
  const dbUrl = `sqlite:///${path.join(tmp, 'e2e.db').replace(/\\/g, '/')}`;
  const teardown = async () => {
    stopAll();
    await new Promise((r) => setTimeout(r, 1000));
    try {
      rmSync(tmp, { recursive: true, force: true });
    } catch {
      /* a log file may still be locked; the OS temp dir cleans up */
    }
  };

  try {
    migrateAndSeed(dbUrl, passwords);
    process.env.GT_DEMO_PASSWORDS_FILE = passwords;

    const apiEnv = {
      ...process.env,
      DATABASE_URL: dbUrl,
      AUTH_REQUIRED: 'true',
      AUTH_COOKIE_SECURE: 'false',
      FRONTEND_URL: WEB,
      CORS_ALLOWED_ORIGINS: WEB,
      PYTHONUNBUFFERED: '1',
    };
    start(venvBin('uvicorn'), ['groundtruth.platform.api.app:app', '--port', String(apiPort)], REPO_ROOT, apiEnv, path.join(tmp, 'api.log'));
    // A worker on the same database, so a run started in the UI is computed, stored and shown (#49).
    start(
      venvBin('python'),
      ['-m', 'apps.worker.main', '--poll-seconds', '0.5', '--pause-before-engine', process.env.E2E_WORKER_PAUSE_S ?? '6'],
      REPO_ROOT,
      { ...apiEnv, WORKER_METRICS_PORT: '0', APP_ENV: 'development' },
      path.join(tmp, 'worker.log'),
    );

    const webEnv = {
      ...process.env,
      NEXT_PUBLIC_API_URL: API,
      INTERNAL_API_URL: API,
      SITE_URL: WEB,
      NEXT_TELEMETRY_DISABLED: '1',
    };
    if (process.env.E2E_SKIP_BUILD !== '1') runSync('npx', ['next', 'build'], WEB_DIR, webEnv);
    start('npx', ['next', 'start', '-p', String(webPort)], WEB_DIR, webEnv, path.join(tmp, 'web.log'), isWin);

    await waitFor(`${API}/health`, 'API', 60_000);
    await waitFor(`${WEB}/login`, 'web app', 60_000);
  } catch (err) {
    await teardown();
    throw err;
  }
  return teardown;
}
