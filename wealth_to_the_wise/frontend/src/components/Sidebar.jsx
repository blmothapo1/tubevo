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
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-30"
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      {/* Sidebar panel — overlay on all screen sizes */}
      <aside
        className={`fixed left-0 top-0 bottom-0 w-64 max-w-[80vw] glass border-r border-surface-300/50 flex flex-col z-40 transition-transform duration-300 ease-[cubic-bezier(0.25,0.1,0.25,1)]
          ${open ? 'translate-x-0' : '-translate-x-full'}`}
      >
        {/* Top gradient accent line */}
        <div className="h-[2px] gradient-brand-accent opacity-60" />

        {/* Logo area */}
        <div className="px-6 py-7 flex items-center justify-between">
          <img src={tubevoLogo} alt="Tubevo" className="h-9" />
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-surface-600 hover:text-white hover:bg-surface-300/50 transition-all duration-200"
          >
            <X size={18} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 space-y-1 mt-2">
          {links.map(({ to, label, icon: Icon }) => {
            const isActive = location.pathname === to;
            return (
              <NavLink
                key={to}
                to={to}
                className="relative flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200"
              >
                {/* Active background indicator */}
                {isActive && (
                  <motion.div
                    layoutId="sidebar-active"
                    className="absolute inset-0 rounded-xl bg-brand-600/12 border border-brand-500/15"
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  />
                )}

                <span className={`relative z-10 transition-colors duration-200 ${isActive ? 'text-brand-400' : 'text-surface-600'}`}>
                  <Icon size={18} />
                </span>
                <span className={`relative z-10 transition-colors duration-200 ${isActive ? 'text-brand-300' : 'text-surface-700 hover:text-surface-900'}`}>
                  {label}
                </span>

                {/* Active left accent bar */}
                {isActive && (
                  <motion.div
                    layoutId="sidebar-accent"
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full gradient-brand"
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  />
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Logout */}
        <div className="px-3 pb-6">
          <button
            onClick={logout}
            className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-surface-600 hover:text-red-400 hover:bg-red-500/8 transition-all duration-200 w-full group"
          >
            <LogOut size={18} className="group-hover:rotate-[-8deg] transition-transform duration-200" />
            Log out
          </button>
        </div>
      </aside>
    </>
  );
}
