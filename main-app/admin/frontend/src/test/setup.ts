import '@testing-library/jest-dom/vitest'

if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => {
      const width = window.innerWidth || 1280
      const minMatch = /\(min-width:\s*(\d+(?:\.\d+)?)px\)/.exec(query)
      const maxMatch = /\(max-width:\s*(\d+(?:\.\d+)?)px\)/.exec(query)
      let matches = Boolean(minMatch || maxMatch)
      if (minMatch && width < Number(minMatch[1])) {
        matches = false
      }
      if (maxMatch && width > Number(maxMatch[1])) {
        matches = false
      }
      return {
        matches,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }
    },
  })
}
