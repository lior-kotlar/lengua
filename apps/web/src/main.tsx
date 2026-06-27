import { StrictMode, Suspense, lazy } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

import App from '@/App';
import { AuthProvider } from '@/components/auth-provider';
import { ThemeProvider } from '@/components/theme-provider';
import { Toaster } from '@/components/ui/toaster';
import { createQueryClient } from '@/lib/query-client';
import '@/index.css';
// Self-hosted diacritic-correct fonts for the complex scripts (group 4.9.2). Bundled by Vite (no
// runtime CDN — mobile-webview-safe): Noto Naskh Arabic positions harakat, Noto Sans Hebrew positions
// nikkud. Only the script subset of each is imported; `font-arabic` / `font-hebrew` (tailwind.config)
// select them for the matching language regions.
import '@fontsource/noto-naskh-arabic/arabic-400.css';
import '@fontsource/noto-naskh-arabic/arabic-700.css';
import '@fontsource/noto-sans-hebrew/hebrew-400.css';
import '@fontsource/noto-sans-hebrew/hebrew-700.css';

const queryClient = createQueryClient();

// Devtools are dev-only: in a production build `import.meta.env.DEV` is false, so the dynamic
// import lives in dead code and is tree-shaken out of the bundle entirely.
const ReactQueryDevtools = import.meta.env.DEV
  ? lazy(() =>
      import('@tanstack/react-query-devtools').then((m) => ({
        default: m.ReactQueryDevtools,
      })),
    )
  : null;

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
        <Toaster />
        {ReactQueryDevtools && (
          <Suspense fallback={null}>
            <ReactQueryDevtools initialIsOpen={false} />
          </Suspense>
        )}
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
