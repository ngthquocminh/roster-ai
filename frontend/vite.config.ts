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
  // `preview` needs the same proxy as `server`, and for the same reason: the
  // application session is a `__Host-`/SameSite cookie (`__Host-shiftmind_session`,
  // see backend/api/auth_security.py) and the API leaves `allow_credentials`
  // at False (D-02), so a cross-origin preview -> :8000 call cannot carry it.
  //
  // README.md, docs/DEVELOPMENT.md and docs/GETTING-STARTED.md all present
  // `npm run preview` as a supported way to drive the production build against
  // a real backend, and `CORS_ORIGINS` has shipped with `4173` in it since v0.4
  // for exactly that. CORS admits the request, but without this proxy the
  // cookie never rides along — so every authenticated surface, which since
  // Epic 1 is all of Scenario Data, silently returns nothing. The proxy makes
  // the documented workflow actually work.
  //
  // It is NOT what the Story 1.11 manual NVDA pass uses: that runs through
  // frontend/e2e/manual-nvda.spec.ts with `installApiStubs`, because the OIDC
  // issuer is a non-routable fake and no browser can be signed in by hand
  // regardless of proxying. See docs/GATE-A-RUNBOOK.md § 3.
  preview: {
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
