#!/usr/bin/env node
/**
 * Issue #58 guard: a `catch` block in api.ts may reference fixture data
 * (MOCK_*) only when that reference is itself gated behind an isDemoMode()
 * check. This is what stops a network failure from silently masquerading as
 * a successful, real result.
 *
 * This is deliberately a structural check (balanced-brace catch-block
 * extraction) rather than a plain `grep -A N`, since a false pass from an
 * arbitrary line-window would defeat the point of having the check at all.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, '..', 'src', 'lib', 'api.ts');
const src = fs.readFileSync(filePath, 'utf8');

function findMatchingBrace(str, openIdx) {
  let depth = 0;
  for (let i = openIdx; i < str.length; i++) {
    if (str[i] === '{') depth++;
    else if (str[i] === '}') {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

const catchRegex = /\bcatch\s*(\([^)]*\))?\s*\{/g;
const violations = [];
let catchCount = 0;
let match;

while ((match = catchRegex.exec(src)) !== null) {
  catchCount += 1;
  const openBrace = match.index + match[0].length - 1;
  const closeBrace = findMatchingBrace(src, openBrace);
  if (closeBrace === -1) {
    console.error(`Unbalanced catch block near offset ${match.index} in ${filePath}`);
    process.exit(1);
  }
  const body = src.slice(openBrace, closeBrace + 1);
  const referencesFixture = /\bMOCK_[A-Z_]+\b/.test(body);
  const gatedByDemoMode = /\bisDemoMode\s*\(\s*\)/.test(body);

  if (referencesFixture && !gatedByDemoMode) {
    const line = src.slice(0, match.index).split('\n').length;
    violations.push(`  src/lib/api.ts:${line} — catch block returns fixture data without an isDemoMode() gate`);
  }
}

if (catchCount === 0) {
  // If api.ts stops having any catch blocks, this check has nothing left to
  // guard and should be revisited rather than silently passing forever.
  console.error('No catch blocks found in src/lib/api.ts — this check is stale, please review it.');
  process.exit(1);
}

if (violations.length > 0) {
  console.error('Fixture fallback guard failed (issue #58):\n');
  console.error(violations.join('\n'));
  console.error(
    '\nA dead backend must never be indistinguishable from a successful run. ' +
      'Gate any catch-block fixture fallback behind isDemoMode().'
  );
  process.exit(1);
}

console.log(`OK: checked ${catchCount} catch block(s) in src/lib/api.ts — no ungated fixture fallback found.`);
