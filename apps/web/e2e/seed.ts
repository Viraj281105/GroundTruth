import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';

/** Repo root: apps/web/e2e -> three levels up. */
export const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');

export function venvBin(name: string): string {
  const dir = process.platform === 'win32' ? 'Scripts' : 'bin';
  const ext = process.platform === 'win32' ? '.exe' : '';
  return path.join(REPO_ROOT, '.venv', dir, name + ext);
}

function run(cmd: string, args: string[], env: NodeJS.ProcessEnv): void {
  const res = spawnSync(cmd, args, { cwd: REPO_ROOT, env, encoding: 'utf8' });
  if (res.status !== 0) {
    // Output never contains passwords: the seed command writes them to a file.
    throw new Error(`${path.basename(cmd)} ${args[0] ?? ''} failed (${res.status}): ${res.stderr || res.stdout}`);
  }
}

/** Migrate a fresh SQLite database and seed the Reference org and the four demo orgs and users. */
export function migrateAndSeed(databaseUrl: string, passwordsFile: string): void {
  const env = { ...process.env, DATABASE_URL: databaseUrl };
  run(
    venvBin('python'),
    ['-c', 'import os; from groundtruth.platform.store.migrate import upgrade; upgrade(os.environ["DATABASE_URL"])'],
    env,
  );
  run(venvBin('groundtruth'), ['seed', '--demo', '--passwords-file', passwordsFile], env);
  grantBenchmark(env);
}

/**
 * The seed grants only Kariba to the demo orgs; the SIMULATED benchmark has no grant, so no demo user could
 * ever see it. Give the NGO (contribute) and funder (view) access so the journeys can check that simulated
 * data is labelled and kept out of real portfolio lists. Test environment only.
 */
function grantBenchmark(env: NodeJS.ProcessEnv): void {
  const code = [
    'import uuid',
    'from datetime import UTC, datetime',
    'from sqlalchemy import select',
    'from groundtruth.platform.store.database import create_db_engine, create_session_factory',
    'from groundtruth.platform.store.models import OrganizationRow, ProjectGrantRow, ProjectRow',
    'S = create_session_factory(create_db_engine())',
    'with S() as db:',
    "    p = db.execute(select(ProjectRow).where(ProjectRow.slug == 'kariba-redd-benchmark')).scalar_one()",
    "    for slug, level in (('demo-ngo', 'contribute'), ('demo-funder', 'view')):",
    '        o = db.execute(select(OrganizationRow).where(OrganizationRow.slug == slug)).scalar_one()',
    '        db.add(ProjectGrantRow(id=str(uuid.uuid4()), project_id=p.id, grantee_organization_id=o.id, level=level, granted_by=None, created_at=datetime.now(UTC).replace(tzinfo=None)))',
    '    db.commit()',
  ].join('\n');
  run(venvBin('python'), ['-c', code], env);
}

export type Persona = 'ngo' | 'funder' | 'auditor' | 'government';

/** Reads the credentials file named by GT_DEMO_PASSWORDS_FILE at test time. Never log the result. */
export function credentialsFor(persona: Persona): { email: string; password: string } {
  const file = process.env.GT_DEMO_PASSWORDS_FILE;
  if (!file) throw new Error('GT_DEMO_PASSWORDS_FILE is not set (e2e/stack.ts sets it)');
  const email = `${persona}@demo.groundtruth.local`;
  for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const [e, p] = line.split('\t');
    if (e === email && p) return { email, password: p };
  }
  throw new Error(`no credentials for ${persona} in the passwords file`);
}
