import { cpSync, existsSync, mkdirSync, readFileSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');

const vendorDir = path.join(rootDir, 'static', 'vendor');
mkdirSync(vendorDir, { recursive: true });

// 1. Bundle Decart Web SDK
const esbuildBin = path.join(
  rootDir,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'esbuild.cmd' : 'esbuild',
);
execFileSync(
  esbuildBin,
  [
    'node_modules/@decartai/sdk/dist/index.js',
    '--bundle',
    '--format=esm',
    '--minify',
    '--legal-comments=eof',
    '--outfile=static/vendor/decart-sdk.js',
  ],
  { cwd: rootDir, stdio: 'inherit', shell: process.platform === 'win32' },
);

// 2. Stage pre-built Xmax Web SDK browser distribution (entry + lazy RTC/COS chunks)
const xmaxSrcDir = path.join(rootDir, 'node_modules', '@xmaxai', 'web-sdk', 'dist', 'browser');
const xmaxDestDir = path.join(vendorDir, 'xmax-sdk');
if (!existsSync(path.join(xmaxSrcDir, 'index.js'))) {
  throw new Error(`Missing @xmaxai/web-sdk browser entry at ${xmaxSrcDir}`);
}
rmSync(xmaxDestDir, { recursive: true, force: true });
cpSync(xmaxSrcDir, xmaxDestDir, { recursive: true });

// 3. Bundle imperative Reactor Web SDK (stubbing optional React/HLS/MP4Box deps for vanilla ESM)
const reactorOut = path.join(vendorDir, 'reactor-sdk.js');
const optionalStubs = {
  react: `
export const createContext = () => ({});
export const useContext = () => undefined;
export const useEffect = () => {};
export const useRef = () => ({ current: null });
export const useState = (v) => [v, () => {}];
export const useMemo = (fn) => fn();
export const useCallback = (fn) => fn;
export const useSyncExternalStore = () => undefined;
`,
  'react/jsx-runtime': `
export const jsx = () => null;
export const jsxs = () => null;
export const Fragment = Symbol('Fragment');
`,
  'hls.js': 'export default {};\n',
  mp4box: 'export default {};\n',
};

await build({
  absWorkingDir: rootDir,
  entryPoints: ['scripts/reactor-entry.mjs'],
  bundle: true,
  format: 'esm',
  minify: true,
  legalComments: 'eof',
  outfile: 'static/vendor/reactor-sdk.js',
  plugins: [
    {
      name: 'stub-reactor-optional-deps',
      setup(buildApi) {
        buildApi.onResolve({ filter: /^(react|react\/jsx-runtime|hls\.js|mp4box)$/ }, (args) => ({
          path: args.path,
          namespace: 'reactor-optional-stub',
        }));
        buildApi.onLoad({ filter: /.*/, namespace: 'reactor-optional-stub' }, (args) => ({
          contents: optionalStubs[args.path] || 'export default {};',
          loader: 'js',
        }));
      },
    },
  ],
});

const reactorBundle = readFileSync(reactorOut, 'utf8');
if (!reactorBundle.trim()) {
  throw new Error('Reactor SDK bundle is empty');
}
for (const pkg of ['"react"', "'react'", '"react/jsx-runtime"', "'react/jsx-runtime'", '"hls.js"', "'hls.js'", '"mp4box"', "'mp4box'"]) {
  if (
    reactorBundle.includes(`from${pkg}`)
    || reactorBundle.includes(`from ${pkg}`)
    || reactorBundle.includes(`import(${pkg})`)
    || reactorBundle.includes(`import${pkg}`)
  ) {
    throw new Error(`Reactor SDK bundle leaked external import ${pkg}`);
  }
}

console.log('Staged Decart, Xmax, and Reactor browser SDKs into static/vendor/');
