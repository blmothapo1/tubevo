import { useState, useEffect, useCallback } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard, Film, CalendarClock, Settings, LogOut, X,
  Tv2, Search, DollarSign, Image, Eye, Mic, Shield,
  ChevronsLeft, ChevronsRight, Command, Radar, BarChart3, Users, Gift,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const SIDEBAR_W_EXPANDED = 260;
const SIDEBAR_W_COLLAPSED = 68;
const LS_KEY = 'tubevo-sidebar-collapsed';

const mainLinks = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/videos', label: 'Videos', icon: Film },
  { to: '/schedule', label: 'Schedule', icon: CalendarClock },
  { to: '/settings', label: 'Settings', icon: Settings },
];

const empireLinks = [
  { to: '/insights', label: 'Insights', icon: BarChart3 },
  { to: '/team', label: 'Team', icon: Users },
  { to: '/trends', label: 'Trend Radar', icon: Radar },
  { to: '/channels', label: 'Channels', icon: Tv2 },
  { to: '/niche', label: 'Niche Intel', icon: Search },
  { to: '/revenue', label: 'Revenue', icon: DollarSign },
  { to: '/thumbnails', label: 'Thumbnails', icon: Image },
  { to: '/competitors', label: 'Competitors', icon: Eye },
  { to: '/voices', label: 'Voice Clones', icon: Mic },
  { to: '/referrals', label: 'Referrals', icon: Gift },
];

/* ── Reusable sidebar link ── */
function SidebarLink({ to, label, icon: Icon, collapsed, onNavigate }) {
  const location = useLocation();
  const isActive = location.pathname === to;

  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      title={collapsed ? label : undefined}
      className={`sidebar-link group relative flex items-center h-[40px] rounded-[10px] text-[13px] font-medium transition-all duration-150
        ${collapsed ? 'justify-center px-0' : 'gap-3 px-3'}`}
    >
      {/* Active background pill */}
      {isActive && (
        <motion.div
          layoutId="sidebar-active"
          className="absolute inset-0 rounded-[10px] bg-brand-500/[0.10]"
          transition={{ type: 'spring', stiffness: 350, damping: 30 }}
        />
      )}
      {/* Left accent bar */}
      {isActive && (
        <motion.div
          layoutId="sidebar-accent"
          className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 rounded-r-sm bg-brand-500"
          transition={{ type: 'spring', stiffness: 350, damping: 30 }}
        />
      )}
      <span className={`relative z-10 shrink-0 transition-colors duration-150 ${isActive ? 'text-brand-400' : 'text-surface-600 group-hover:text-surface-800'}`}>
        <Icon size={18} />
      </span>
      {!collapsed && (
        <motion.span
          initial={{ opacity: 0, x: -4 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.15, delay: 0.05 }}
          className={`relative z-10 truncate transition-colors duration-150 ${isActive ? 'text-white' : 'text-surface-700 group-hover:text-surface-900'}`}
        >
          {label}
        </motion.span>
      )}

      {/* Tooltip on collapsed hover */}
      {collapsed && (
        <div className="sidebar-tooltip">
          {label}
        </div>
      )}
    </NavLink>
  );
}

/* ── Expanded content for mobile drawer ── */
function MobileSidebarContent({ onNavigate, onClose }) {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === 'admin';
  const initials = (user?.full_name || user?.email || '?')
    .split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2);

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 h-[60px] flex items-center justify-between shrink-0">
        <span className="text-[18px] font-semibold text-white" style={{ fontFamily: "'Poppins', sans-serif" }}>
          Tubevo
        </span>
        <button onClick={onClose}
          className="p-1.5 rounded-[6px] text-surface-600 hover:text-white hover:bg-white/[0.04] transition-colors">
          <X size={16} />
        </button>
      </div>
      <nav className="flex-1 px-3 space-y-0.5 overflow-y-auto scrollbar-none">
        {mainLinks.map((link) => (
          <SidebarLink key={link.to} {...link} collapsed={false} onNavigate={onNavigate} />
        ))}
        <div className="pt-4 mt-4 border-t border-[var(--border-subtle)]">
          <p className="px-3 mb-2 text-[10px] font-semibold text-surface-500 uppercase tracking-[0.08em]">Empire OS</p>
          {empireLinks.map((link) => (
            <SidebarLink key={link.to} {...link} collapsed={false} onNavigate={onNavigate} />
          ))}
        </div>
        {isAdmin && (
          <div className="pt-4 mt-4 border-t border-[var(--border-subtle)]">
            <SidebarLink to="/admin" label="Admin HQ" icon={Shield} collapsed={false} onNavigate={onNavigate} />
          </div>
        )}
      </nav>
      <div className="px-3 pb-4 pt-3 border-t border-[var(--border-subtle)] shrink-0">
        <div className="flex items-center gap-3 px-3 py-2 mb-1 rounded-[8px]">
          <div className="w-8 h-8 rounded-[8px] bg-brand-500 flex items-center justify-center text-[11px] font-semibold text-white/90 select-none shrink-0">{initials}</div>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-medium text-surface-900 truncate">{user?.full_name || 'User'}</p>
            <p className="text-[11px] text-surface-600 truncate">{user?.email}</p>
          </div>
        </div>
        <button onClick={logout}
          className="flex items-center gap-3 h-[38px] px-3 rounded-[8px] text-[13px] font-medium text-surface-600 hover:text-red-400 hover:bg-red-500/8 transition-colors duration-150 w-full">
          <LogOut size={16} /> Log out
        </button>
      </div>
    </div>
  );
}

/* ── Desktop sidebar — collapsible icon rail ── */
function DesktopSidebar({ collapsed, onToggle, onCommandPalette }) {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === 'admin';
  const initials = (user?.full_name || user?.email || '?')
    .split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2);

  return (
    <motion.aside
      animate={{ width: collapsed ? SIDEBAR_W_COLLAPSED : SIDEBAR_W_EXPANDED }}
      transition={{ type: 'spring', stiffness: 400, damping: 32 }}
      className="hidden lg:flex lg:fixed lg:left-0 lg:top-0 lg:bottom-0 lg:z-30 lg:flex-col sidebar-surface overflow-hidden"
    >
      <div className="flex flex-col h-full">
        {/* Logo row */}
        <div className={`h-[60px] flex items-center shrink-0 ${collapsed ? 'justify-center px-0' : 'px-5 justify-between'}`}>
          {collapsed ? (
            <div className="w-8 h-8 rounded-[8px] bg-brand-500/15 flex items-center justify-center">
              <span className="text-[14px] font-bold text-brand-400" style={{ fontFamily: "'Poppins', sans-serif" }}>T</span>
            </div>
          ) : (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.1 }}
              className="text-[18px] font-semibold text-white"
              style={{ fontFamily: "'Poppins', sans-serif" }}
            >
              Tubevo
            </motion.span>
          )}
          {!collapsed && (
            <motion.button
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.1 }}
              onClick={onToggle}
              className="p-1.5 rounded-[6px] text-surface-500 hover:text-white hover:bg-white/[0.04] transition-colors"
              title="Collapse sidebar"
            >
              <ChevronsLeft size={16} />
            </motion.button>
          )}
        </div>

        {/* ⌘K shortcut button */}
        <div className={`${collapsed ? 'px-2' : 'px-3'} mb-2`}>
          <button
            onClick={onCommandPalette}
            className={`w-full flex items-center h-[36px] rounded-[8px] text-[12px] font-medium text-surface-500 hover:text-surface-700 hover:bg-white/[0.03] transition-all duration-150
              ${collapsed ? 'justify-center px-0' : 'gap-2.5 px-3'}`}
            title={collapsed ? 'Search (⌘K)' : undefined}
          >
            <Command size={14} className="shrink-0" />
            {!collapsed && (
              <>
                <span className="flex-1 text-left">Search…</span>
                <kbd className="text-[10px] text-surface-500 bg-white/[0.04] px-1.5 py-0.5 rounded font-mono">⌘K</kbd>
              </>
            )}
          </button>
        </div>

        {/* Navigation */}
        <nav className={`flex-1 space-y-0.5 overflow-y-auto scrollbar-none ${collapsed ? 'px-2' : 'px-3'}`}>
          {mainLinks.map((link) => (
            <SidebarLink key={link.to} {...link} collapsed={collapsed} onNavigate={() => {}} />
          ))}

          <div className="pt-4 mt-4 border-t border-[var(--border-subtle)]">
            {!collapsed && (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="px-3 mb-2 text-[10px] font-semibold text-surface-500 uppercase tracking-[0.08em]"
              >
                Empire OS
              </motion.p>
            )}
            {empireLinks.map((link) => (
              <SidebarLink key={link.to} {...link} collapsed={collapsed} onNavigate={() => {}} />
            ))}
          </div>

          {isAdmin && (
            <div className="pt-4 mt-4 border-t border-[var(--border-subtle)]">
              <SidebarLink to="/admin" label="Admin HQ" icon={Shield} collapsed={collapsed} onNavigate={() => {}} />
            </div>
          )}
        </nav>

        {/* Footer — user + collapse toggle */}
        <div className={`pb-3 pt-3 border-t border-[var(--border-subtle)] shrink-0 ${collapsed ? 'px-2' : 'px-3'}`}>
          {/* User avatar */}
          <div className={`flex items-center rounded-[8px] py-2 mb-1 ${collapsed ? 'justify-center px-0' : 'gap-3 px-3'}`}
            title={collapsed ? `${user?.full_name || 'User'}\n${user?.email}` : undefined}>
            <div className="w-8 h-8 rounded-[8px] bg-brand-500 flex items-center justify-center text-[11px] font-semibold text-white/90 select-none shrink-0">
              {initials}
            </div>
            {!collapsed && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-surface-900 truncate">{user?.full_name || 'User'}</p>
                <p className="text-[11px] text-surface-600 truncate">{user?.email}</p>
              </motion.div>
            )}
          </div>

          {/* Logout */}
          <button onClick={logout} title={collapsed ? 'Log out' : undefined}
            className={`flex items-center h-[38px] rounded-[8px] text-[13px] font-medium text-surface-600 hover:text-red-400 hover:bg-red-500/8 transition-colors duration-150 w-full
              ${collapsed ? 'justify-center px-0' : 'gap-3 px-3'}`}>
            <LogOut size={16} />
            {!collapsed && <span>Log out</span>}
          </button>

          {/* Expand button — only in collapsed mode */}
          {collapsed && (
            <button onClick={onToggle}
              className="flex items-center justify-center h-[38px] rounded-[8px] text-surface-500 hover:text-white hover:bg-white/[0.04] transition-colors duration-150 w-full mt-1"
              title="Expand sidebar">
              <ChevronsRight size={16} />
            </button>
          )}
        </div>
      </div>
    </motion.aside>
  );
}

export { SIDEBAR_W_EXPANDED, SIDEBAR_W_COLLAPSED };

export default function Sidebar({ open, onClose, collapsed, onToggleCollapse, onCommandPalette }) {
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

      {/* ── Mobile drawer ── */}
      <aside
        className={`fixed left-0 top-0 bottom-0 w-[260px] max-w-[80vw] z-50 lg:hidden
          sidebar-surface transition-transform duration-200 ease-out
          ${open ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <MobileSidebarContent onNavigate={onClose} onClose={onClose} />
      </aside>

      {/* ── Desktop — collapsible rail ── */}
      <DesktopSidebar collapsed={collapsed} onToggle={onToggleCollapse} onCommandPalette={onCommandPalette} />
    </>
  );
}
