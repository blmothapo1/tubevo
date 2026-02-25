import { useState, useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import OnboardingTutorial from './OnboardingTutorial';
import useOnboarding from '../hooks/useOnboarding';

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const { showTutorial, completeTutorial } = useOnboarding();

  // Auto-close sidebar on any route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-surface-50">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      {/* No lg:ml-64 — sidebar is overlay-only, content is always centered */}
      <div className="min-h-screen flex flex-col">
        <Topbar onMenuToggle={() => setSidebarOpen((prev) => !prev)} />
        <motion.main
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.25, 0.1, 0.25, 1] }}
          className="flex-1 w-full max-w-6xl mx-auto p-5 sm:p-8"
        >
          <Outlet />
        </motion.main>
      </div>

      {/* Onboarding tutorial overlay — additive, no existing logic modified */}
      <AnimatePresence>
        {showTutorial && (
          <OnboardingTutorial onComplete={completeTutorial} />
        )}
      </AnimatePresence>
    </div>
  );
}
