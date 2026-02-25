import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { Wifi, WifiOff, UserCircle, Menu } from 'lucide-react';

export default function Topbar({ onMenuToggle }) {
  const { user } = useAuth();
  const [connection, setConnection] = useState(null);

  useEffect(() => {
    async function fetchStatus() {
      try {
        const { data } = await api.get('/oauth/youtube/status');
        setConnection(data);
      } catch {
        // Not connected or service unavailable — leave null
      }
    }
    fetchStatus();
  }, []);

  const connected = connection?.connected;
  const initials = (user?.full_name || user?.email || '?')
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <header className="h-16 border-b border-surface-300/50 glass sticky top-0 z-20 flex items-center justify-between px-5 sm:px-8">
      <div className="flex items-center gap-3 min-w-0">
        {/* Hamburger menu — visible on all screen sizes */}
        <button
          onClick={onMenuToggle}
          data-tour="menu-button"
          className="p-2 -ml-2 rounded-lg text-surface-600 hover:text-white hover:bg-surface-300/50 transition-all duration-200"
        >
          <Menu size={20} />
        </button>

        {/* YouTube connection status pill */}
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 ${
          connected
            ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
            : 'bg-surface-200/80 border border-surface-300 text-surface-600'
        }`}>
          {connected ? (
            <>
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-soft-pulse absolute inline-flex h-full w-full rounded-full bg-emerald-400" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
              </span>
              <span className="hidden sm:inline truncate max-w-[140px]">
                {connection.channel_title || 'YouTube Connected'}
              </span>
              <span className="sm:hidden">Connected</span>
            </>
          ) : (
            <>
              <WifiOff size={12} />
              <span className="hidden sm:inline">No channel</span>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <span className="text-sm text-surface-700 truncate max-w-[140px] hidden sm:inline">
          {user?.full_name || user?.email}
        </span>
        <div className="w-9 h-9 rounded-xl gradient-brand flex items-center justify-center shadow-soft text-xs font-semibold text-white/90 select-none">
          {initials}
        </div>
      </div>
    </header>
  );
}
