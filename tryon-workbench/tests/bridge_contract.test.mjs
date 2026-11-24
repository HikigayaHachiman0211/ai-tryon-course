import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = await readFile(resolve(here, '..', 'static', 'js', 'script.js'), 'utf8');
const mainSource = await readFile(resolve(here, '..', 'main.py'), 'utf8');

test('Workbench bridge accepts and sends messages only to configured origins', () => {
  assert.match(source, /function isTrustedBridgeOrigin\(origin\)/);
  assert.match(source, /if \(!current\) return false/);
  assert.match(source, /recommendOriginFromConfig\(\)/);
  assert.match(source, /target\.postMessage\([\s\S]*?, origin\)/);
  assert.doesNotMatch(source, /postMessage\([\s\S]*?,\s*['"]\*['"]\)/);
  assert.doesNotMatch(source, /targetOrigin\s*=\s*['"]\*['"]/);
  assert.doesNotMatch(source, /new URL\(rawReturnUrl\)/);
});

test('Workbench production CORS is configured from exact origins', () => {
  assert.match(mainSource, /CORS_ALLOW_ORIGINS/);
  assert.match(mainSource, /CORS_ALLOW_ORIGINS must contain exact origins in production/);
  assert.match(mainSource, /allow_origins=\["\*"\] if allow_all_origins else cors_origins/);
  assert.match(mainSource, /allow_credentials=not allow_all_origins/);
});
