import { useState, useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import OnboardingTutorial from './OnboardingTutorial';
import useOnboarding from '../hooks/useOnboarding';
import { DeviceDebugOverlay } from '../hooks/useDevice.jsx';

/* Map routes to page titles for the topbar breadcrumb */
const PAGE_TITLES = {
  '/dashboard': 'Dashboard',
  '/videos': 'Videos',
  '/schedule': 'Automation',
  '/settings': 'Settings',
  '/channels': 'Channels',
  '/niche': 'Niche Intel',
  '/revenue': 'Revenue',
  '/thumbnails': 'Thumbnails',
  '/competitors': 'Competitors',
  '/voices': 'Voice Clones',
};

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const { showTutorial, completeTutorial } = useOnboarding();

  // Auto-close mobile sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  const pageTitle = PAGE_TITLES[location.pathname] || '';

  return (
    <div className="min-h-screen bg-surface-50 overflow-safe">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Main content — offset on desktop to account for persistent sidebar */}
      <div className="min-h-screen flex flex-col lg:ml-[260px]">
        <Topbar
          onMenuToggle={() => setSidebarOpen((prev) => !prev)}
          pageTitle={pageTitle}
        />
        <motion.main
          key={location.pathname}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
          className="flex-1 w-full max-w-6xl mx-auto px-5 py-5 sm:px-6 sm:py-6 lg:px-8 lg:py-8 safe-area-inset"
        >
          <Outlet />
        </motion.main>
      </div>

      {/* Onboarding tutorial overlay */}
      <AnimatePresence>
        {showTutorial && (
          <OnboardingTutorial onComplete={completeTutorial} />
        )}
      </AnimatePresence>

      {/* Dev debug overlay — only shows in dev mode with ?debug=device */}
      <DeviceDebugOverlay />
    </div>
  );
}
