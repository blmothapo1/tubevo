import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { WifiOff, Menu, ChevronRight } from 'lucide-react';

export default function Topbar({ onMenuToggle, pageTitle }) {
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
    <header
      className="h-[60px] topbar-surface sticky top-0 z-20 flex items-center justify-between"
      style={{
        paddingLeft: 'clamp(32px, 10vw, 44px)',
        paddingRight: 'clamp(32px, 10vw, 44px)',
      }}
    >
      <div className="flex items-center gap-3 min-w-0">
        {/* Hamburger — mobile only (sidebar is persistent on desktop) */}
        <button
          onClick={onMenuToggle}
          data-tour="menu-button"
          className="p-1.5 -ml-1.5 rounded-[6px] text-surface-600 hover:text-white hover:bg-white/[0.04] transition-colors duration-150 lg:hidden"
        >
          <Menu size={18} />
        </button>

        {/* Page title breadcrumb */}
        {pageTitle && (
          <div className="flex items-center gap-1.5 text-[13px]">
            <span className="text-surface-600 hidden sm:inline">Tubevo</span>
            <ChevronRight size={12} className="text-surface-500 hidden sm:inline" />
            <span className="text-surface-900 font-medium">{pageTitle}</span>
          </div>
        )}

        {/* YouTube connection status pill */}
        <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-[6px] text-[11px] font-medium tracking-wide uppercase transition-colors duration-150 ml-auto sm:ml-3 ${
          connected
            ? 'bg-emerald-500/8 text-emerald-400'
            : 'bg-surface-200 text-surface-600'
        }`}>
          {connected ? (
            <>
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ripple absolute inline-flex h-full w-full rounded-full text-emerald-400" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
              </span>
              <span className="hidden sm:inline truncate max-w-[140px]">
                {connection.channel_title || 'Connected'}
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

      {/* Right side — user info (hidden on desktop since sidebar has user profile) */}
      <div className="flex items-center gap-3 shrink-0 lg:hidden">
        <div className="w-8 h-8 rounded-[8px] bg-brand-500 flex items-center justify-center text-[11px] font-semibold text-white/90 select-none">
          {initials}
        </div>
      </div>
    </header>
  );
}
