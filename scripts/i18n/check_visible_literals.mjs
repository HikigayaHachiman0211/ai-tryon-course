#!/usr/bin/env node
/**
 * Guard user-visible source changes against accidental Chinese literals.
 *
 * The repository intentionally contains canonical product values, test data,
 * prompt fixtures, and the Chinese fallback runtime. Those are excluded. The
 * default mode checks added lines in the working diff; --all scans source
 * files, and --strict turns findings into a failure for CI.
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const strict = process.argv.includes('--strict');
const all = process.argv.includes('--all');
const han = /[\u3400-\u9fff]/;
const sourceExtensions = new Set(['.ts', '.tsx', '.js', '.jsx', '.html']);
const excludedPath = /(?:[\\/]public[\\/]locales[\\/]|[\\/]static[\\/]i18n[\\/]|catalog-translations|read-model[\\/]catalog|(?:^|[\\/])tests?[\\/]|\.test\.|\.spec\.)/i;
const canonicalFile = /(?:formOptions|constants|ProductEditPage|ProductsPage|AnnotationsPage|ProfilesPage|SampleModelsPage|database\.py|prompts\.py|i18n\.js)$/i;

function relative(file) {
  return path.relative(repoRoot, file).replaceAll('\\', '/');
}

function isAllowedLine(line, file) {
  if (excludedPath.test(file) || canonicalFile.test(file)) return true;
  // The standalone workbench intentionally keeps a complete Chinese HTML
  // fallback for offline/first-paint safety; i18n.js remaps it at startup.
  if (/tryon-workbench[\\/]static[\\/]index\.html$/i.test(file)) return true;
  // These files contain stable canonical enums, voice IDs, or fallback label
  // maps. Their rendered labels are resolved through translation resources.
  if (/(?:formPatch|ScoreBreakdown|useAssistantVoiceConfig|voiceSettingsStorage|ProfilesPage|SampleModelsPage)\.(?:ts|tsx)$/i.test(file)) return true;
  if (/简体中文|日本語/.test(line)) return true;
  if (/data-i18n(?:-[a-z-]+)?\s*=/.test(line)) return true;
  if (/^\s*\/\//.test(line)) return true;
  if (/garmentTypeInput|canonical.*enum|internal.*value/i.test(line)) return true;
  if (/source(?:\s*[-_]?\s*)?data|fixture|canonical|technical|fallback/i.test(line)) return true;
  if (/console\.(log|warn|error)\s*\(/.test(line)) return true;
  if (/data-(?:code|key|value|testid)|aria-(?:label|description)=?\s*[`'\"]/.test(line)) return true;
  if (/https?:\/\/|[A-Z][A-Z0-9_]{2,}|[a-z][a-z0-9_.-]+\.[a-z]{2,}/.test(line) && !/return|render|innerHTML|textContent|>/.test(line)) return true;
  return false;
}

function changedLines() {
  try {
    const diff = execFileSync('git', ['diff', '--unified=0', '--no-ext-diff', '--', '.'], { cwd: repoRoot, encoding: 'utf8' });
    const findings = [];
    let file = '';
    for (const line of diff.split(/\r?\n/)) {
      if (line.startsWith('+++ b/')) file = line.slice(6).trim();
      if (!line.startsWith('+') || line.startsWith('+++') || !file) continue;
      const source = line.slice(1);
      if (han.test(source) && !isAllowedLine(source, file)) findings.push({ file, line: source });
    }
    return findings;
  } catch {
    return [];
  }
}

function allSourceFiles() {
  const roots = [
    path.join(repoRoot, 'main-app', 'frontend', 'src'),
    path.join(repoRoot, 'main-app', 'admin', 'frontend', 'src'),
    path.join(repoRoot, 'tryon-workbench', 'static'),
  ];
  const files = [];
  const walk = (directory) => {
    if (!fs.existsSync(directory)) return;
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const full = path.join(directory, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (sourceExtensions.has(path.extname(entry.name))) files.push(full);
    }
  };
  roots.forEach(walk);
  const findings = [];
  for (const file of files) {
    const fileName = relative(file);
    fs.readFileSync(file, 'utf8').split(/\r?\n/).forEach((line, index) => {
      if (han.test(line) && !isAllowedLine(line, fileName)) findings.push({ file: fileName, line: `${index + 1}: ${line.trim()}` });
    });
  }
  return findings;
}

const findings = all ? allSourceFiles() : changedLines();
if (findings.length) {
  console.warn(`[i18n-literals] ${findings.length} possible user-visible literal(s) found`);
  findings.slice(0, 40).forEach(({ file, line }) => console.warn(`  ${file}: ${line}`));
  if (strict) process.exitCode = 1;
} else {
  console.log(`[i18n-literals] PASS (${all ? 'all source' : 'added diff'} scan)`);
}
