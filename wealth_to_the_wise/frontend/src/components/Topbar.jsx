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

  return (
    <header className="h-14 sm:h-16 border-b border-surface-300 bg-surface-100/80 backdrop-blur-sm flex items-center justify-between px-4 sm:px-6 sticky top-0 z-20">
      <div className="flex items-center gap-2 sm:gap-3 min-w-0">
        {/* Hamburger — mobile only */}
        <button
          onClick={onMenuToggle}
          className="lg:hidden p-2 -ml-2 text-surface-600 hover:text-white transition-colors"
        >
          <Menu size={20} />
        </button>

        <span className="hidden sm:inline text-sm text-surface-700">Channel:</span>
        <span className="text-xs sm:text-sm font-medium text-surface-900 truncate max-w-[120px] sm:max-w-none">
          {connected ? (connection.channel_title || 'YouTube Channel') : 'Not connected'}
        </span>
        {connected ? (
          <span className="flex items-center gap-1 text-xs text-emerald-400">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span className="hidden sm:inline"><Wifi size={14} className="inline" /> Connected</span>
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-surface-600">
            <WifiOff size={14} />
            <span className="hidden sm:inline">Disconnected</span>
          </span>
        )}
      </div>

      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        <span className="text-xs sm:text-sm text-surface-700 truncate max-w-[100px] sm:max-w-none hidden sm:inline">
          {user?.full_name || user?.email}
        </span>
        <div className="w-8 h-8 rounded-full gradient-brand flex items-center justify-center">
          <UserCircle size={20} className="text-white/80" />
        </div>
      </div>
    </header>
  );
}
