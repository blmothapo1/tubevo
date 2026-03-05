import { NavLink, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard, Film, CalendarClock, Settings, LogOut, X,
  Tv2, Search, DollarSign, Image, Eye, Mic, Shield,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const mainLinks = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/videos', label: 'Videos', icon: Film },
  { to: '/schedule', label: 'Automation', icon: CalendarClock },
  { to: '/settings', label: 'Settings', icon: Settings },
];

const empireLinks = [
  { to: '/channels', label: 'Channels', icon: Tv2 },
  { to: '/niche', label: 'Niche Intel', icon: Search },
  { to: '/revenue', label: 'Revenue', icon: DollarSign },
  { to: '/thumbnails', label: 'Thumbnails', icon: Image },
  { to: '/competitors', label: 'Competitors', icon: Eye },
  { to: '/voices', label: 'Voice Clones', icon: Mic },
];

/* ── Reusable sidebar link with animated active indicator ── */
function SidebarLink({ to, label, icon: Icon, size = 18, onNavigate }) {
  const location = useLocation();
  const isActive = location.pathname === to;

  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      className="relative flex items-center gap-3 h-[40px] px-3 rounded-[8px] text-[13px] font-medium transition-colors duration-150 group"
    >
      {isActive && (
        <motion.div
          layoutId="sidebar-active"
          className="absolute inset-0 rounded-[8px] bg-brand-500/[0.10]"
          transition={{ type: 'tween', duration: 0.2, ease: 'easeOut' }}
        />
      )}
      <span className={`relative z-10 transition-colors duration-150 ${isActive ? 'text-brand-400' : 'text-surface-600 group-hover:text-surface-800'}`}>
        <Icon size={size} />
      </span>
      <span className={`relative z-10 transition-colors duration-150 ${isActive ? 'text-white' : 'text-surface-700 group-hover:text-surface-900'}`}>
        {label}
      </span>
      {isActive && (
        <motion.div
          layoutId="sidebar-accent"
          className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 rounded-r-sm bg-brand-500"
          transition={{ type: 'tween', duration: 0.2, ease: 'easeOut' }}
        />
      )}
    </NavLink>
  );
}

/* ── Sidebar inner content — shared between mobile drawer & desktop panel ── */
function SidebarContent({ onNavigate, showClose, onClose }) {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === 'admin';

  const initials = (user?.full_name || user?.email || '?')
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="flex flex-col h-full">
      {/* Logo row */}
      <div className="px-5 h-[60px] flex items-center justify-between shrink-0">
        <span className="text-[18px] font-semibold text-white" style={{ fontFamily: "'Poppins', sans-serif" }}>
          Tubevo
        </span>
        {showClose && (
          <button
            onClick={onClose}
            className="p-1.5 rounded-[6px] text-surface-600 hover:text-white hover:bg-white/[0.04] transition-colors"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 space-y-0.5 overflow-y-auto scrollbar-none">
        {mainLinks.map((link) => (
          <SidebarLink key={link.to} {...link} onNavigate={onNavigate} />
        ))}

        {/* Empire OS section */}
        <div className="pt-4 mt-4 border-t border-[var(--border-subtle)]">
          <p className="px-3 mb-2 text-[10px] font-semibold text-surface-500 uppercase tracking-[0.08em]">
            Empire OS
          </p>
          {empireLinks.map((link) => (
            <SidebarLink key={link.to} {...link} size={16} onNavigate={onNavigate} />
          ))}
        </div>

        {/* Admin link — only for admins */}
        {isAdmin && (
          <div className="pt-4 mt-4 border-t border-[var(--border-subtle)]">
            <SidebarLink to="/admin" label="Admin HQ" icon={Shield} size={16} onNavigate={onNavigate} />
          </div>
        )}
      </nav>

      {/* User profile + Logout */}
      <div className="px-3 pb-4 pt-3 border-t border-[var(--border-subtle)] shrink-0">
        <div className="flex items-center gap-3 px-3 py-2 mb-1 rounded-[8px]">
          <div className="w-8 h-8 rounded-[8px] bg-brand-500 flex items-center justify-center text-[11px] font-semibold text-white/90 select-none shrink-0">
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-medium text-surface-900 truncate">{user?.full_name || 'User'}</p>
            <p className="text-[11px] text-surface-600 truncate">{user?.email}</p>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex items-center gap-3 h-[38px] px-3 rounded-[8px] text-[13px] font-medium text-surface-600 hover:text-red-400 hover:bg-red-500/8 transition-colors duration-150 w-full"
        >
          <LogOut size={16} />
          Log out
        </button>
      </div>
    </div>
  );
}

export default function Sidebar({ open, onClose }) {
  return (
    <>
      {/* ── Mobile backdrop ── */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden"
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      {/* ── Mobile drawer (overlay) ── */}
      <aside
        className={`fixed left-0 top-0 bottom-0 w-[260px] max-w-[80vw] z-50 lg:hidden
          sidebar-surface transition-transform duration-200 ease-out
          ${open ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <SidebarContent onNavigate={onClose} showClose onClose={onClose} />
      </aside>

      {/* ── Desktop persistent sidebar ── */}
      <aside className="hidden lg:flex lg:fixed lg:left-0 lg:top-0 lg:bottom-0 lg:w-[260px] lg:z-30 lg:flex-col sidebar-surface">
        <SidebarContent onNavigate={() => {}} showClose={false} />
      </aside>
    </>
  );
}
