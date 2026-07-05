import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Stable vendor chunks: framework code lands in long-lived chunks so app-code edits don't
        // bust them, and the React.lazy route chunks (App.tsx) don't each re-bundle React. Keep
        // react + react-dom + the router together so ONE React instance is shared (a duplicated
        // React across chunks breaks hooks).
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'react-query': ['@tanstack/react-query'],
          supabase: ['@supabase/supabase-js'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    css: true,
    // Playwright specs under e2e/ (and the live-staging specs under e2e-staging/) are run by
    // Playwright, not vitest. The src-only include already excludes them; this is belt-and-braces.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', 'dist', 'e2e/**', 'e2e-staging/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json-summary', 'lcov'],
      all: true,
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.d.ts',
        'src/**/*.{test,spec}.{ts,tsx}',
        'src/main.tsx',
        'src/vite-env.d.ts',
        // Exclude the presentational shadcn primitives (all .tsx), but keep use-toast.ts — the one
        // .ts module here, a real reducer/store with its own unit test (use-toast.test.ts).
        'src/components/ui/**/*.tsx',
      ],
      thresholds: {
        lines: 80,
        branches: 80,
        functions: 80,
        statements: 80,
      },
    },
  },
});
