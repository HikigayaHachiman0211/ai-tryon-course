import { readFileSync, readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { expect, it } from 'vitest'

function files(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    return entry.isDirectory() ? files(path) : /\.(ts|tsx)$/.test(path) && !/\.(test|spec)\./.test(path) ? [path] : []
  })
}

it('resolves every literal translation key used by the main and admin interfaces in Japanese', () => {
  const missing: string[] = []
  for (const root of [process.cwd(), resolve(process.cwd(), '../admin/frontend')]) {
    for (const file of files(join(root, 'src'))) {
      const source = readFileSync(file, 'utf8')
      const namespace = source.match(/useTranslation\(\s*(?:\[\s*)?['"]([^'"]+)/)?.[1] || 'common'
      for (const match of source.matchAll(/\bt\(\s*['"]([\w.:-]+)['"]/g)) {
        const [ns, key] = match[1].includes(':') ? match[1].split(':', 2) : [namespace, match[1]]
        let value: unknown = JSON.parse(readFileSync(join(root, 'public/locales/ja', `${ns}.json`), 'utf8'))
        for (const part of key.split('.')) value = value && typeof value === 'object' ? (value as Record<string, unknown>)[part] : undefined
        if (typeof value !== 'string') missing.push(`${file}: ${match[1]}`)
      }
    }
  }
  expect(missing).toEqual([])
})
