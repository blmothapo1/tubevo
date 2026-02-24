import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Film, CalendarClock, Settings, LogOut, Menu, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import tubevoLogo from '../assets/tubevo-logo-web.png';

const links = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/videos', label: 'Videos', icon: Film },
  { to: '/schedule', label: 'Schedule', icon: CalendarClock },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar({ open, onToggle }) {
  const { logout } = useAuth();

  return (
    <>
      {/* Mobile backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={onToggle}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed left-0 top-0 bottom-0 w-60 bg-surface-100 border-r border-surface-300 flex flex-col z-40 transition-transform duration-200 ease-in-out
          ${open ? 'translate-x-0' : '-translate-x-full'}
          lg:translate-x-0`}
      >
        {/* Accent gradient line at top */}
        <div className="h-0.5 gradient-brand-accent" />

        <div className="px-5 py-6 flex items-center justify-between">
          <img src={tubevoLogo} alt="Tubevo" className="h-7" />
          {/* Close button on mobile */}
          <button onClick={onToggle} className="lg:hidden p-1 text-surface-600 hover:text-white transition-colors">
            <X size={20} />
          </button>
        </div>

        <nav className="flex-1 px-3 space-y-1">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={onToggle}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-brand-600/15 text-brand-400'
                    : 'text-surface-700 hover:text-surface-900 hover:bg-surface-200'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 pb-5">
          <button
            onClick={logout}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-surface-600 hover:text-red-400 hover:bg-surface-200 transition-colors w-full"
          >
            <LogOut size={18} />
            Log out
          </button>
        </div>
      </aside>
    </>
  );
}
