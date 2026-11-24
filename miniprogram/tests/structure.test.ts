import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const MP_ROOT = path.resolve(__dirname, '../miniprogram');

function walkFiles(dir: string): string[] {
  const results: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkFiles(full));
    } else if (entry.isFile()) {
      results.push(full);
    }
  }
  return results;
}

describe('WeChat Mini Program structural integrity and size budget', () => {
  it('all declared pages and custom-tab-bar files exist', () => {
    const appJson = JSON.parse(fs.readFileSync(path.join(MP_ROOT, 'app.json'), 'utf8')) as {
      pages: string[];
      tabBar?: { custom?: boolean; list?: Array<{ pagePath: string }> };
    };
    expect(appJson.pages.length).toBeGreaterThanOrEqual(7);
    for (const pagePath of appJson.pages) {
      for (const ext of ['.ts', '.json', '.wxml', '.wxss']) {
        expect(fs.existsSync(path.join(MP_ROOT, `${pagePath}${ext}`))).toBe(true);
      }
    }
    if (appJson.tabBar?.custom) {
      for (const ext of ['.ts', '.json', '.wxml', '.wxss']) {
        expect(fs.existsSync(path.join(MP_ROOT, `custom-tab-bar/index${ext}`))).toBe(true);
      }
    }
  });

  it('uses no bare * universal selectors in wxss, no browser DOM globals in code, and stays well below 2MB', () => {
    const files = walkFiles(MP_ROOT);
    let totalBytes = 0;

    for (const file of files) {
      const stat = fs.statSync(file);
      totalBytes += stat.size;
      const content = fs.readFileSync(file, 'utf8');

      if (file.endsWith('.wxss')) {
        expect(content).not.toMatch(/(^|\n)\s*\*\s*\{/);
      }
      if (file.endsWith('.ts')) {
        expect(content).not.toMatch(/\b(window|document)\./);
        expect(content).not.toMatch(/\bnew\s+(FormData|URL)\b/);
      }
    }

    // Main package limit is 2MB (2,097,152 bytes)
    expect(totalBytes).toBeLessThan(2 * 1024 * 1024);
  });
});
