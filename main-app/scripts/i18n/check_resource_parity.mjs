#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';

const localeNames = ['zh-CN', 'en', 'ja'];
const localeRoot = path.resolve(process.cwd(), 'public', 'locales');

function fail(message) {
  console.error(`[i18n-parity] ${message}`);
  process.exitCode = 1;
}

function parseJson(text, filename) {
  let index = 0;
  const duplicatePaths = [];
  const error = (message) => { throw new Error(`${filename}:${index + 1}: ${message}`); };
  const skip = () => { while (/\s/.test(text[index] || '')) index += 1; };
  const parseString = () => {
    const start = index;
    if (text[index] !== '"') error('expected string');
    index += 1;
    while (index < text.length) {
      if (text[index] === '\\') { index += 2; continue; }
      if (text[index] === '"') {
        index += 1;
        return JSON.parse(text.slice(start, index));
      }
      index += 1;
    }
    error('unterminated string');
  };
  const parseValue = (currentPath) => {
    skip();
    const char = text[index];
    if (char === '"') return parseString();
    if (char === '{') {
      index += 1;
      const result = {};
      const seen = new Set();
      skip();
      if (text[index] === '}') { index += 1; return result; }
      while (index < text.length) {
        skip();
        const key = parseString();
        if (seen.has(key)) duplicatePaths.push(`${currentPath}.${key}`);
        seen.add(key);
        skip();
        if (text[index] !== ':') error('expected colon');
        index += 1;
        result[key] = parseValue(`${currentPath}.${key}`);
        skip();
        if (text[index] === '}') { index += 1; return result; }
        if (text[index] !== ',') error('expected comma');
        index += 1;
      }
      error('unterminated object');
    }
    if (char === '[') {
      index += 1;
      const result = [];
      skip();
      if (text[index] === ']') { index += 1; return result; }
      while (index < text.length) {
        result.push(parseValue(`${currentPath}[${result.length}]`));
        skip();
        if (text[index] === ']') { index += 1; return result; }
        if (text[index] !== ',') error('expected comma');
        index += 1;
      }
      error('unterminated array');
    }
    const literal = text.slice(index).match(/^(true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/);
    if (!literal) error('invalid value');
    index += literal[0].length;
    return JSON.parse(literal[0]);
  };
  const value = parseValue('$');
  skip();
  if (index !== text.length) error('trailing content');
  if (duplicatePaths.length) throw new Error(`${filename}: duplicate keys ${duplicatePaths.join(', ')}`);
  return value;
}

function flatten(value, prefix = '') {
  const output = new Map();
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      for (const [key, child] of flatten(item, `${prefix}[${index}]`)) output.set(key, child);
    });
    return output;
  }
  if (value && typeof value === 'object') {
    for (const [key, childValue] of Object.entries(value)) {
      const child = prefix ? `${prefix}.${key}` : key;
      for (const [flatKey, flatValue] of flatten(childValue, child)) output.set(flatKey, flatValue);
    }
    return output;
  }
  output.set(prefix, value);
  return output;
}

function interpolationSet(value) {
  return [...String(value ?? '').matchAll(/\{\{\s*([\w.-]+)\s*\}\}/g)].map((match) => match[1]).sort().join('|');
}

if (!fs.existsSync(localeRoot)) {
  fail(`missing locale directory: ${localeRoot}`);
  process.exit();
}

const filesByLocale = Object.fromEntries(localeNames.map((locale) => [
  locale,
  fs.readdirSync(path.join(localeRoot, locale)).filter((name) => name.endsWith('.json')).sort(),
]));
const expectedFiles = filesByLocale['zh-CN'];
for (const locale of localeNames) {
  if (JSON.stringify(filesByLocale[locale]) !== JSON.stringify(expectedFiles)) {
    fail(`${locale} namespace set differs from zh-CN`);
  }
}

for (const namespace of expectedFiles) {
  const flattened = {};
  for (const locale of localeNames) {
    const filename = path.join(localeRoot, locale, namespace);
    try {
      flattened[locale] = flatten(parseJson(fs.readFileSync(filename, 'utf8'), filename));
    } catch (error) {
      fail(error.message);
      continue;
    }
  }
  if (!flattened['zh-CN'] || !flattened.en || !flattened.ja) continue;
  const baseKeys = [...flattened['zh-CN'].keys()].sort();
  for (const locale of ['en', 'ja']) {
    const keys = [...flattened[locale].keys()].sort();
    if (JSON.stringify(keys) !== JSON.stringify(baseKeys)) fail(`${namespace}: ${locale} key set differs from zh-CN`);
  }
  for (const key of baseKeys) {
    const values = localeNames.map((locale) => flattened[locale].get(key));
    values.forEach((value, index) => {
      if (typeof value === 'string' && (!value.trim() || value.trim() === key)) {
        fail(`${namespace}:${key}: empty/key-identical value in ${localeNames[index]}`);
      }
    });
    const variables = values.map(interpolationSet);
    if (new Set(variables).size !== 1) fail(`${namespace}:${key}: interpolation variables differ`);
  }
}

if (!process.exitCode) console.log(`[i18n-parity] PASS (${expectedFiles.length} namespaces, locales: ${localeNames.join(', ')})`);
