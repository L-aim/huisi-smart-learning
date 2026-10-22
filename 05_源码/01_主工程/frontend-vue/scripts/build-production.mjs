import { fileURLToPath, URL } from 'node:url'
import { build } from 'vite'
import vue from '@vitejs/plugin-vue'


// Loading vite.config.ts makes esbuild scan parent folders on some restricted
// Windows environments. Supplying the equivalent config programmatically keeps
// the normal production output while avoiding that environment-dependent scan.
const root = process.cwd()

await build({
  root,
  configFile: false,
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('../src', import.meta.url)),
    },
  },
  build: {
    sourcemap: 'hidden',
  },
})

