import { Route, Routes } from 'react-router-dom';

import { AppLayout } from '@/components/app-layout';
import { AuthLayout } from '@/components/auth-layout';
import Account from '@/pages/Account';
import Dashboard from '@/pages/Dashboard';
import Discover from '@/pages/Discover';
import Generate from '@/pages/Generate';
import Languages from '@/pages/Languages';
import Login from '@/pages/Login';
import NotFound from '@/pages/NotFound';
import Review from '@/pages/Review';
import Settings from '@/pages/Settings';
import Signup from '@/pages/Signup';

export default function App() {
  return (
    <Routes>
      {/* Unauthenticated auth routes (no app shell). Forms land in group 4.3. */}
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
      </Route>

      {/* Authenticated app routes (shared app shell). Route gating lands in group 4.3. */}
      <Route element={<AppLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/generate" element={<Generate />} />
        <Route path="/review" element={<Review />} />
        <Route path="/discover" element={<Discover />} />
        <Route path="/languages" element={<Languages />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/account" element={<Account />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
