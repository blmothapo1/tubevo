import { useState, useEffect, useCallback } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import Sidebar, { SIDEBAR_W_EXPANDED, SIDEBAR_W_COLLAPSED } from './Sidebar';
import Topbar from './Topbar';
import CommandPalette from './CommandPalette';
import OnboardingTutorial from './OnboardingTutorial';
import useOnboarding from '../hooks/useOnboarding';
import { DeviceDebugOverlay } from '../hooks/useDevice.jsx';

const LS_KEY = 'tubevo-sidebar-collapsed';
const LG_BREAKPOINT = 1024; // Tailwind's lg: breakpoint

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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { return localStorage.getItem(LS_KEY) === '1'; } catch { return false; }
  });
  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false);
  const [isDesktop, setIsDesktop] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= LG_BREAKPOINT : true
  );
  const location = useLocation();
  const navigate = useNavigate();
  const { showTutorial, completeTutorial } = useOnboarding();

  // Track viewport size to gate sidebar margin animation
  useEffect(() => {
    const mql = window.matchMedia(`(min-width: ${LG_BREAKPOINT}px)`);
    const onChange = (e) => setIsDesktop(e.matches);
    mql.addEventListener('change', onChange);
    setIsDesktop(mql.matches);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  // Persist sidebar collapse preference
  const toggleCollapse = useCallback(() => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try { localStorage.setItem(LS_KEY, next ? '1' : '0'); } catch { /* */ }
      return next;
    });
  }, []);

  // ⌘K global shortcut
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCmdPaletteOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Auto-close mobile sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  const pageTitle = PAGE_TITLES[location.pathname] || '';
  const sidebarWidth = sidebarCollapsed ? SIDEBAR_W_COLLAPSED : SIDEBAR_W_EXPANDED;

  return (
    <div className="min-h-screen bg-surface-50 overflow-safe">
      {/* Ambient gradient mesh — living background */}
      <div className="ambient-mesh" aria-hidden="true" />

      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        collapsed={sidebarCollapsed}
        onToggleCollapse={toggleCollapse}
        onCommandPalette={() => setCmdPaletteOpen(true)}
      />

      {/* Main content — offset for sidebar on desktop only */}
      <motion.div
        animate={{ marginLeft: isDesktop ? `${sidebarWidth}px` : '0px' }}
        transition={{ type: 'spring', stiffness: 400, damping: 32 }}
        className="min-h-screen flex flex-col"
      >
        <Topbar
          onMenuToggle={() => setSidebarOpen((prev) => !prev)}
          pageTitle={pageTitle}
        />
        <motion.main
          key={location.pathname}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
          className="flex-1 w-full max-w-6xl mx-auto"
          style={{
            paddingLeft: 'clamp(16px, 5vw, 32px)',
            paddingRight: 'clamp(16px, 5vw, 32px)',
            paddingTop: 'clamp(20px, 4vw, 32px)',
            paddingBottom: 'clamp(20px, 4vw, 32px)',
          }}
        >
          <Outlet />
        </motion.main>
      </motion.div>

      {/* ⌘K Command Palette */}
      <CommandPalette
        open={cmdPaletteOpen}
        onClose={() => setCmdPaletteOpen(false)}
        onNavigate={(path) => { setCmdPaletteOpen(false); navigate(path); }}
      />

      {/* Onboarding tutorial overlay */}
      <AnimatePresence>
        {showTutorial && (
          <OnboardingTutorial onComplete={completeTutorial} />
        )}
      </AnimatePresence>

      <DeviceDebugOverlay />
    </div>
  );
}
