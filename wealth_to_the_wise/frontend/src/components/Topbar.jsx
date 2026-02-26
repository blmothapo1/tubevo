import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { Wifi, WifiOff, UserCircle, Menu } from 'lucide-react';
import tubevoLogo from '../assets/tubevo-logo-web.png';

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
    <header className="h-14 border-b border-surface-300 glass sticky top-0 z-20 flex items-center justify-between px-4 sm:px-6 lg:px-8 safe-area-inset">
      <div className="flex items-center gap-3 min-w-0">
        {/* Hamburger menu — visible on all screen sizes */}
        <button
          onClick={onMenuToggle}
          data-tour="menu-button"
          className="p-1.5 -ml-1.5 rounded text-surface-600 hover:text-white hover:bg-surface-300/60 transition-colors duration-150"
        >
          <Menu size={18} />
        </button>

        {/* Logo — always visible in the topbar */}
        <img src={tubevoLogo} alt="Tubevo" className="h-7 sm:h-8 shrink-0" />

        {/* YouTube connection status pill */}
        <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium tracking-wide uppercase transition-colors duration-150 ${
          connected
            ? 'bg-emerald-500/8 border border-emerald-500/20 text-emerald-400'
            : 'bg-surface-200 border border-surface-300 text-surface-600'
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
              <span className="sm:hidden">Live</span>
            </>
          ) : (
            <>
              <WifiOff size={10} />
              <span className="hidden sm:inline">Offline</span>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <span className="text-xs text-surface-600 truncate max-w-[140px] hidden sm:inline">
          {user?.full_name || user?.email}
        </span>
        <div className="w-8 h-8 rounded bg-brand-500 flex items-center justify-center text-[11px] font-semibold text-white/90 select-none">
          {initials}
        </div>
      </div>
    </header>
  );
}
