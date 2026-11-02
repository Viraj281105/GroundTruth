#!/usr/bin/env node
/**
 * Issue #17 guard: the committed TypeScript API types must be exactly what the
 * generator produces from the committed OpenAPI snapshot.
 *
 * The UI must never hand-write a backend shape. This fails when someone changed
 * src/lib/generated/openapi.json without regenerating, or edited schema.d.ts by
 * hand. (The Python test suite checks the other half: that openapi.json is what
 * the API actually serves.)
 *
 * It regenerates into a temporary file with the same command `npm run
 * generate:api` uses and compares the two, ignoring only CRLF/LF differences so
 * a Windows checkout cannot fail it falsely.
 */
'use strict';

const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const root = path.join(__dirname, '..');
const snapshot = path.join(root, 'src', 'lib', 'generated', 'openapi.json');
const committed = path.join(root, 'src', 'lib', 'generated', 'schema.d.ts');
const generatorPkg = path.join(root, 'node_modules', 'openapi-typescript', 'package.json');
const cli = path.join(root, 'node_modules', 'openapi-typescript', 'bin', 'cli.js');

const REGENERATE =
  'Regenerate with `make api-types` (or `npm run generate:api` in apps/web) and commit the result.';

for (const [file, what] of [
  [snapshot, 'the OpenAPI snapshot'],
  [committed, 'the generated types'],
  [cli, 'openapi-typescript (run `npm ci`)'],
]) {
  if (!fs.existsSync(file)) {
    console.error(`API types check: ${what} is missing (${path.relative(root, file)}).`);
    process.exit(1);
  }
}

// The output depends on the generator version, which package.json pins exactly.
const pinned = require(path.join(root, 'package.json')).devDependencies['openapi-typescript'];
const installed = require(generatorPkg).version;
if (pinned !== installed) {
  console.error(
    `API types check: openapi-typescript ${installed} is installed but ${pinned} is pinned. Run \`npm ci\`.`
  );
  process.exit(1);
}

// Use exactly the arguments `npm run generate:api` uses, read from package.json, so
// the check and the generator can never disagree about flags. Only the output path
// is redirected, to a temporary file.
const command = require(path.join(root, 'package.json')).scripts['generate:api'].trim().split(/\s+/);
if (command[0] !== 'openapi-typescript' || command.indexOf('-o') === -1) {
  console.error('API types check: the generate:api script is not `openapi-typescript <in> -o <out> ...`.');
  process.exit(1);
}
const args = command.slice(1);

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'groundtruth-api-types-'));
const fresh = path.join(tmp, 'schema.d.ts');
args[args.indexOf('-o') + 1] = fresh;
try {
  execFileSync(process.execPath, [cli, ...args], { cwd: root, stdio: 'pipe' });
  const normalise = (text) => text.replace(/\r\n/g, '\n');
  const expected = normalise(fs.readFileSync(fresh, 'utf8'));
  const actual = normalise(fs.readFileSync(committed, 'utf8'));
  if (expected !== actual) {
    const a = actual.split('\n');
    const e = expected.split('\n');
    const line = a.findIndex((text, i) => text !== e[i]);
    console.error('API types check failed: src/lib/generated/schema.d.ts is stale or was edited by hand.');
    console.error(`First difference at line ${line + 1}:`);
    console.error(`  committed: ${JSON.stringify(a[line])}`);
    console.error(`  expected:  ${JSON.stringify(e[line])}`);
    console.error(REGENERATE);
    process.exit(1);
  }
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}

console.log('OK: src/lib/generated/schema.d.ts matches the OpenAPI snapshot.');
