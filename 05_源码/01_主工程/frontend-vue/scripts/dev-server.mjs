import { Agent } from 'node:http'
import { fileURLToPath, URL } from 'node:url'
import { createServer } from 'vite'
import vue from '@vitejs/plugin-vue'


function argument(name, fallback) {
  const index = process.argv.indexOf(name)
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback
}

const host = argument('--host', '127.0.0.1')
const port = Number(argument('--port', '5173'))
const root = process.cwd()
const backendAgent = new Agent({ keepAlive: true, maxSockets: 32, maxFreeSockets: 8 })
const backendProxy = {
  target: 'http://127.0.0.1:8000',
  changeOrigin: true,
  ws: true,
  agent: backendAgent,
}

const server = await createServer({
  root,
  configFile: false,
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('../src', import.meta.url)),
    },
  },
  server: {
    host,
    port,
    strictPort: true,
    proxy: {
      '/api': backendProxy,
      '/files': backendProxy,
      '/exports': backendProxy,
    },
  },
})

await server.listen()
server.printUrls()

