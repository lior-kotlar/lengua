import { Route, Routes } from 'react-router-dom';

import { AppLayout } from '@/components/app-layout';
import { AuthLayout } from '@/components/auth-layout';
import { RedirectIfAuthed, RequireAuth } from '@/components/route-guards';
import Account from '@/pages/Account';
import AuthCallback from '@/pages/AuthCallback';
import Dashboard from '@/pages/Dashboard';
import Discover from '@/pages/Discover';
import ForgotPassword from '@/pages/ForgotPassword';
import Generate from '@/pages/Generate';
import Languages from '@/pages/Languages';
import Login from '@/pages/Login';
import NotFound from '@/pages/NotFound';
import Review from '@/pages/Review';
import ResetPassword from '@/pages/ResetPassword';
import Settings from '@/pages/Settings';
import Signup from '@/pages/Signup';

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

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
