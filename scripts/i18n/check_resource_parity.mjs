#!/usr/bin/env node
// The implementation lives with the application sources. This root wrapper
// also makes the same gate usable from the Git root or either frontend.
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const implementation = path.join(repoRoot, 'main-app', 'scripts', 'i18n', 'check_resource_parity.mjs');
const localResources = path.join(process.cwd(), 'public', 'locales');

if (fs.existsSync(localResources)) {
  await import(pathToFileURL(implementation));
} else {
  const adminOnly = process.argv.includes('--admin');
  const mainOnly = process.argv.includes('--main');
  const targets = adminOnly
    ? ['admin/frontend']
    : mainOnly
      ? ['frontend']
      : ['frontend', 'admin/frontend'];
  for (const target of targets) {
    const result = spawnSync(process.execPath, [implementation], {
      cwd: path.join(repoRoot, 'main-app', target),
      stdio: 'inherit',
    });
    if (result.status) process.exitCode = result.status;
  }
}
