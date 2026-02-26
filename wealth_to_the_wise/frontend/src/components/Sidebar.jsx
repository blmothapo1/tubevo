import { NavLink, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { LayoutDashboard, Film, CalendarClock, Settings, LogOut, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

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
        className={`fixed left-0 top-0 bottom-0 w-[240px] max-w-[80vw] glass flex flex-col z-40 transition-transform duration-200 ease-out
          ${open ? 'translate-x-0' : '-translate-x-full'}`}
      >

        {/* Logo area */}
        <div className="px-5 py-5 flex items-center justify-between">
          <span className="text-[20px] font-semibold text-white" style={{ fontFamily: "'Poppins', sans-serif" }}>Tubevo</span>
          <button
            onClick={onClose}
            className="p-1 rounded-[8px] text-surface-600 hover:text-white hover:bg-white/[0.04] transition-colors duration-150"
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
                className="relative flex items-center gap-3 h-[40px] px-3 rounded-[8px] text-[13px] font-medium transition-colors duration-150"
              >
                {/* Active background indicator */}
                {isActive && (
                  <motion.div
                    layoutId="sidebar-active"
                    className="absolute inset-0 rounded-[8px] bg-brand-500/[0.15]"
                    transition={{ type: 'tween', duration: 0.2, ease: 'easeOut' }}
                  />
                )}

                <span className={`relative z-10 transition-colors duration-150 ${isActive ? 'text-brand-400' : 'text-surface-600'}`}>
                  <Icon size={18} />
                </span>
                <span className={`relative z-10 transition-colors duration-150 ${isActive ? 'text-brand-300' : 'text-surface-700 hover:text-surface-900'}`}>
                  {label}
                </span>

                {/* Active left accent bar */}
                {isActive && (
                  <motion.div
                    layoutId="sidebar-accent"
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 rounded-r-sm bg-brand-500"
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
            className="flex items-center gap-3 h-[40px] px-3 rounded-[8px] text-[13px] font-medium text-surface-600 hover:text-red-400 hover:bg-red-500/8 transition-colors duration-150 w-full"
          >
            <LogOut size={18} />
            Log out
          </button>
        </div>
      </aside>
    </>
  );
}
