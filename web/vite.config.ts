import react from '@vitejs/plugin-react'
import { configDefaults, defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/run': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // Playwright specs live under e2e/ and use @playwright/test's own
    // test()/expect(), not Vitest's — keep them out of `npx vitest run`.
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
})
