import { NavLink, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { LayoutDashboard, Film, CalendarClock, Settings, LogOut, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import tubevoLogo from '../assets/tubevo-logo-web.png';

const links = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/videos', label: 'Videos', icon: Film },
  { to: '/schedule', label: 'Schedule', icon: CalendarClock },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar({ open, onClose }) {
  const { logout } = useAuth();
  const location = useLocation();

  return (
    <>
      {/* Backdrop — blurred overlay on all screen sizes */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-30"
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      {/* Sidebar panel — overlay on all screen sizes */}
      <aside
        className={`fixed left-0 top-0 bottom-0 w-60 max-w-[80vw] glass border-r border-surface-300 flex flex-col z-40 transition-transform duration-200 ease-out
          ${open ? 'translate-x-0' : '-translate-x-full'}`}
      >
        {/* Top accent line */}
        <div className="h-[1px] gradient-brand-accent opacity-50" />

        {/* Logo area */}
        <div className="px-5 py-5 flex items-center justify-between">
          <img src={tubevoLogo} alt="Tubevo" className="h-8" />
          <button
            onClick={onClose}
            className="p-1 rounded text-surface-600 hover:text-white hover:bg-surface-300/60 transition-colors duration-150"
          >
            <X size={16} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 space-y-0.5 mt-1">
          {links.map(({ to, label, icon: Icon }) => {
            const isActive = location.pathname === to;
            return (
              <NavLink
                key={to}
                to={to}
                className="relative flex items-center gap-3 px-3 py-2.5 rounded text-[13px] font-medium transition-colors duration-150"
              >
                {/* Active background indicator */}
                {isActive && (
                  <motion.div
                    layoutId="sidebar-active"
                    className="absolute inset-0 rounded bg-brand-500/10 border border-brand-500/15"
                    transition={{ type: 'tween', duration: 0.2, ease: 'easeOut' }}
                  />
                )}

                <span className={`relative z-10 transition-colors duration-150 ${isActive ? 'text-brand-400' : 'text-surface-600'}`}>
                  <Icon size={16} />
                </span>
                <span className={`relative z-10 transition-colors duration-150 ${isActive ? 'text-brand-300' : 'text-surface-700 hover:text-surface-900'}`}>
                  {label}
                </span>

                {/* Active left accent bar */}
                {isActive && (
                  <motion.div
                    layoutId="sidebar-accent"
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 rounded-r-sm gradient-brand"
                    transition={{ type: 'tween', duration: 0.2, ease: 'easeOut' }}
                  />
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Logout */}
        <div className="px-3 pb-5">
          <button
            onClick={logout}
            className="flex items-center gap-3 px-3 py-2.5 rounded text-[13px] font-medium text-surface-600 hover:text-red-400 hover:bg-red-500/8 transition-colors duration-150 w-full"
          >
            <LogOut size={16} />
            Log out
          </button>
        </div>
      </aside>
    </>
  );
}
