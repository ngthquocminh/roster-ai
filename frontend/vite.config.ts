import path from 'node:path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
// Vitest reads this file natively (defineConfig from 'vitest/config' merges
// the `test` block's types on top of Vite's own) — one config file means the
// `@` alias and plugins cannot drift between build and test.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // The parity guard renders all 1,547 demand rows while axe sweeps run in
    // other files. Bounding workers avoids CPU starvation without relaxing
    // that guard's assertions or timeout.
    maxWorkers: 4,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
    // `src/lib/env.ts` throws loudly at import time if VITE_API_BASE_URL is
    // unset (deliberately — see that file). Tests must not depend on a
    // developer's local, gitignored `.env`; this is a fixed test-only value,
    // never read by `npm run dev`/`build` (those load real `.env` files via
    // Vite's own mechanism, unaffected by this `test`-scoped block).
    env: {
      VITE_API_BASE_URL: 'http://localhost:5173',
    },
  },
})
