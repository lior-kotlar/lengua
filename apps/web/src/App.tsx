import { lazy } from 'react';
import { Route, Routes } from 'react-router-dom';

import { AppLayout } from '@/components/app-layout';
import { AuthLayout } from '@/components/auth-layout';
import { RedirectIfAuthed, RequireAuth } from '@/components/route-guards';
import { StaticLayout } from '@/components/static-layout';
import AuthCallback from '@/pages/AuthCallback';
import Dashboard from '@/pages/Dashboard';
import DeleteAccount from '@/pages/DeleteAccount';
import ForgotPassword from '@/pages/ForgotPassword';
import Login from '@/pages/Login';
import NotFound from '@/pages/NotFound';
import Privacy from '@/pages/Privacy';
import ResetPassword from '@/pages/ResetPassword';
import Signup from '@/pages/Signup';
import Support from '@/pages/Support';

// Code-split the authenticated, non-landing screens: each becomes its own chunk fetched on first
// navigation, so the initial load (auth pages + Dashboard) ships less JavaScript. Every page is an
// `export default`, so React.lazy consumes it directly. The Suspense fallback lives around the app
// shell's <Outlet /> (see AppLayout), so only the routed content shows the skeleton while a chunk
// loads — the header + nav stay mounted. Dashboard, the auth screens, and NotFound stay eager.
const Account = lazy(() => import('@/pages/Account'));
const Discover = lazy(() => import('@/pages/Discover'));
const Generate = lazy(() => import('@/pages/Generate'));
const Languages = lazy(() => import('@/pages/Languages'));
const Review = lazy(() => import('@/pages/Review'));
const Settings = lazy(() => import('@/pages/Settings'));

export default function App() {
  return (
    <Routes>
      {/* Public auth routes (no app shell). A signed-in user is bounced into the app, which is
          also how a successful login/OAuth redirects (the forms don't navigate themselves). */}
      <Route element={<RedirectIfAuthed />}>
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
        </Route>
      </Route>

      {/* Recovery + verification/OAuth landing run with a transient session, so they are NOT
          redirect-guarded (that would bounce the user before they finish). */}
      <Route element={<AuthLayout />}>
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
      </Route>

      {/* Authenticated app routes (shared app shell), gated by RequireAuth → redirect to /login. */}
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/generate" element={<Generate />} />
          <Route path="/review" element={<Review />} />
          <Route path="/discover" element={<Discover />} />
          <Route path="/languages" element={<Languages />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/account" element={<Account />} />
        </Route>
      </Route>

      {/* Public static/content pages — reachable WITHOUT signing in: the store-required Privacy +
          Support URLs and the external account-deletion form (Google Play requires a deletion path
          usable without the app). */}
      <Route element={<StaticLayout />}>
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/support" element={<Support />} />
        <Route path="/delete-account" element={<DeleteAccount />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
