import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Film, CalendarClock, Settings, LogOut } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const links = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/videos', label: 'Videos', icon: Film },
  { to: '/schedule', label: 'Schedule', icon: CalendarClock },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar() {
  const { logout } = useAuth();

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-60 bg-surface-100 border-r border-surface-300 flex flex-col z-30">
      <div className="px-5 py-6">
        <span className="text-xl font-bold tracking-tight text-white">
          <span className="text-brand-400">Tube</span>vo
        </span>
      </div>

      <nav className="flex-1 px-3 space-y-1">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
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
  );
}
