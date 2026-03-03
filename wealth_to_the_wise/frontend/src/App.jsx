import { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';

import Landing from './pages/Landing';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Onboarding from './pages/Onboarding';
import Dashboard from './pages/Dashboard';
import Videos from './pages/Videos';
import Schedule from './pages/Schedule';
import Settings from './pages/Settings';
import GoogleCallback from './pages/GoogleCallback';
import AppleCallback from './pages/AppleCallback';
import Privacy from './pages/Privacy';
import Terms from './pages/Terms';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import AdminHQ from './pages/AdminHQ';
import AdminUsers from './pages/AdminUsers';
import AdminVideos from './pages/AdminVideos';
import AdminErrors from './pages/AdminErrors';
import AdminWaitlist from './pages/AdminWaitlist';

import DashboardLayout from './components/DashboardLayout';
import ProtectedRoute from './components/ProtectedRoute';
import AdminRoute from './components/AdminRoute';
import { initTheme } from './theme/theme';

export default function App() {
  useEffect(() => {
    const cleanup = initTheme();
    return cleanup;
  }, []);

  return (
    <BrowserRouter>
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
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
