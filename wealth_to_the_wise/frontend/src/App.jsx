import { useEffect, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import DashboardLayout from './components/DashboardLayout';
import ProtectedRoute from './components/ProtectedRoute';
import AdminRoute from './components/AdminRoute';
import PageLoader from './components/PageLoader';
import { initTheme } from './theme/theme';

/* ── Lazy-loaded pages (code-split into separate chunks) ──────────── */
const Landing        = lazy(() => import('./pages/Landing'));
const Login          = lazy(() => import('./pages/Login'));
const Signup         = lazy(() => import('./pages/Signup'));
const Onboarding     = lazy(() => import('./pages/Onboarding'));
const Dashboard      = lazy(() => import('./pages/Dashboard'));
const Videos         = lazy(() => import('./pages/Videos'));
const Schedule       = lazy(() => import('./pages/Schedule'));
const Settings       = lazy(() => import('./pages/Settings'));
const GoogleCallback = lazy(() => import('./pages/GoogleCallback'));
const AppleCallback  = lazy(() => import('./pages/AppleCallback'));
const Privacy        = lazy(() => import('./pages/Privacy'));
const Terms          = lazy(() => import('./pages/Terms'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const ResetPassword  = lazy(() => import('./pages/ResetPassword'));
const AdminHQ        = lazy(() => import('./pages/AdminHQ'));
const AdminUsers     = lazy(() => import('./pages/AdminUsers'));
const AdminVideos    = lazy(() => import('./pages/AdminVideos'));
const AdminErrors    = lazy(() => import('./pages/AdminErrors'));
const AdminWaitlist  = lazy(() => import('./pages/AdminWaitlist'));
const Channels       = lazy(() => import('./pages/Channels'));
const NicheIntel     = lazy(() => import('./pages/NicheIntel'));
const Revenue        = lazy(() => import('./pages/Revenue'));
const Thumbnails     = lazy(() => import('./pages/Thumbnails'));
const Competitors    = lazy(() => import('./pages/Competitors'));
const VoiceClones    = lazy(() => import('./pages/VoiceClones'));
const TrendRadar     = lazy(() => import('./pages/TrendRadar'));
const Insights       = lazy(() => import('./pages/Insights'));
const Team           = lazy(() => import('./pages/Team'));
const Referrals      = lazy(() => import('./pages/Referrals'));
const NotFound       = lazy(() => import('./pages/NotFound'));

export default function App() {
  useEffect(() => {
    const cleanup = initTheme();
    return cleanup;
  }, []);

  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route
            path="/auth/google/callback"
            element={
              <ProtectedRoute>
                <GoogleCallback />
              </ProtectedRoute>
            }
          />
          <Route path="/apple-callback" element={<AppleCallback />} />

          {/* Admin route — server-verified role=admin required */}
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <AdminHQ />
              </AdminRoute>
            }
          />
          <Route
            path="/admin/users"
            element={
              <AdminRoute>
                <AdminUsers />
              </AdminRoute>
            }
          />
          <Route
            path="/admin/videos"
            element={
              <AdminRoute>
                <AdminVideos />
              </AdminRoute>
            }
          />
          <Route
            path="/admin/errors"
            element={
              <AdminRoute>
                <AdminErrors />
              </AdminRoute>
            }
          />
          <Route
            path="/admin/waitlist"
            element={
              <AdminRoute>
                <AdminWaitlist />
              </AdminRoute>
            }
          />

          {/* Protected routes */}
          <Route
            path="/onboarding"
            element={
              <ProtectedRoute>
                <Onboarding />
              </ProtectedRoute>
            }
          />

          <Route
            element={
              <ProtectedRoute>
                <DashboardLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/videos" element={<Videos />} />
            <Route path="/schedule" element={<Schedule />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/channels" element={<Channels />} />
            <Route path="/niche" element={<NicheIntel />} />
            <Route path="/revenue" element={<Revenue />} />
            <Route path="/thumbnails" element={<Thumbnails />} />
            <Route path="/competitors" element={<Competitors />} />
            <Route path="/voices" element={<VoiceClones />} />
            <Route path="/trends" element={<TrendRadar />} />
            <Route path="/insights" element={<Insights />} />
            <Route path="/team" element={<Team />} />
            <Route path="/referrals" element={<Referrals />} />
          </Route>

          {/* 404 catch-all — must be last */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
