// Read an existing Vue toolchain; all generated output stays in this checkout.
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { resolve, dirname } from 'node:path'
import { readFile, mkdir, writeFile, readdir } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'

const root = resolve(process.env.THREE_MM_APP_PROJECT || resolve(import.meta.dirname, '..'))
const config = JSON.parse(await readFile(resolve(root, 'app-development.json'), 'utf8'))
const dependencies = process.env.THREE_MM_FRONTEND_ROOT
const host = process.env.THREE_MM_PUBLIC_HOST
if (!dependencies || !host) throw new Error('Set THREE_MM_FRONTEND_ROOT and THREE_MM_PUBLIC_HOST to the read-only toolchain and public host source')
const require = createRequire(resolve(dependencies, 'package.json'))
const load = name => import(pathToFileURL(require.resolve(name)).href)
const { build } = await load('vite')
const { default: vue } = await load('@vitejs/plugin-vue')
const out = resolve(process.env.THREE_MM_APP_CHECK_OUTPUT || resolve(root, '.runtime/local-profile'))
const stage = process.env.THREE_MM_APP_STAGE
if (!stage) throw new Error('Run tools/check_application.py so the checked package sources are staged first')
const contract = JSON.parse(await readFile(resolve(stage, 'compiled-ui.json'), 'utf8'))
await mkdir(out, { recursive: true })
const publicRoot = resolve(out, 'public-source')
await mkdir(resolve(publicRoot, 'assets'), { recursive: true })
await writeFile(resolve(publicRoot, 'assets/ui-platform.css'), await readFile(resolve(dirname(host), '../assets/ui-platform.css')))
for (const directory of ['extension-ui', 'components/ui']) {
  const source = resolve(dirname(host), '..', directory)
  for (const name of await readdir(source)) {
    if (!(/^Ui.*\.vue$/.test(name) || ['context.ts', 'v1.ts', 'application-v1.ts'].includes(name))) continue
    const target = resolve(publicRoot, directory, name)
    await mkdir(dirname(target), { recursive: true })
    await writeFile(target, await readFile(resolve(source, name)))
  }
}
const hostSnapshot = resolve(publicRoot, 'extension-ui/application-v1.ts')
const uiSnapshot = resolve(publicRoot, 'extension-ui/v1.ts')
const tsconfig = resolve(out, 'tsconfig.json')
await writeFile(tsconfig, JSON.stringify({ compilerOptions: {
  target: 'ES2022', module: 'ESNext', moduleResolution: 'Bundler', strict: true, skipLibCheck: true,
  lib: ['ES2022', 'DOM', 'DOM.Iterable'], resolveJsonModule: true, esModuleInterop: true, noEmit: true, types: [], baseUrl: root,
  paths: { vue: [resolve(dependencies, 'node_modules/vue/dist/vue.d.ts')], '@3mm/application-ui/v1': [hostSnapshot], '@3mm/ui/v1': [uiSnapshot] }
}, include: config.frontend_inputs.flatMap(path => [resolve(root, path, '**/*.ts'), resolve(root, path, '**/*.vue')]) }))
const checked = spawnSync(process.execPath, [require.resolve('vue-tsc/bin/vue-tsc.js'), '-p', tsconfig, '--noEmit'], { cwd: root, stdio: 'inherit' })
if (checked.status !== 0) process.exit(checked.status || 1)
await build({ configFile: false, root, publicDir: false, plugins: [vue()], build: {
  outDir: resolve(out, 'ui'), emptyOutDir: true, cssCodeSplit: false,
  rollupOptions: { input: Object.fromEntries(contract.entrypoints.map(item => [item.entrypoint_id, resolve(stage, item.source)])),
    external: ['vue', '@3mm/application-ui/v1', '@3mm/ui/v1'], preserveEntrySignatures: 'strict', output: { format: 'es', entryFileNames: '[name].mjs' } }
} })
const { createVitest } = await load('vitest/node')
const vitest = await createVitest('test', { root, config: false, watch: false,
  include: config.frontend_tests, environment: 'jsdom', pool: 'forks', maxWorkers: 1, minWorkers: 1 }, {
  plugins: [vue()], resolve: { alias: { '@3mm/application-ui/v1': hostSnapshot, '@3mm/ui/v1': uiSnapshot,
    vue: resolve(dependencies, 'node_modules/vue/dist/vue.runtime.esm-bundler.js'),
    '@vue/test-utils': resolve(dirname(require.resolve('@vue/test-utils')), 'vue-test-utils.esm-bundler.mjs'),
    vitest: resolve(dirname(require.resolve('vitest/package.json')), 'dist/index.js') } },
  cacheDir: resolve(out, 'vite-cache')
})
let testCount = 0
try {
  await vitest.start()
  const leaves = task => task.type === 'test' ? [task] : (task.tasks || []).flatMap(leaves)
  const tests = vitest.state.getFiles().flatMap(leaves)
  testCount = tests.length
  if (!testCount || tests.some(test => test.result?.state !== 'pass') || vitest.state.getUnhandledErrors().length) process.exitCode = 1
} finally { await vitest.close() }
await writeFile(resolve(out, 'frontend-check.json'), JSON.stringify({ node: process.versions.node,
  vue: JSON.parse(await readFile(require.resolve('vue/package.json'), 'utf8')).version,
  vite: JSON.parse(await readFile(require.resolve('vite/package.json'), 'utf8')).version,
  test_count: testCount, typecheck: 'passed', build: 'passed', tests: process.exitCode ? 'failed' : 'passed' }, null, 2))
