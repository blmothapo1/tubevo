import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { Wifi, WifiOff, UserCircle } from 'lucide-react';

export default function Topbar() {
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
    <header className="h-16 border-b border-surface-300 bg-surface-100/80 backdrop-blur-sm flex items-center justify-between px-6 sticky top-0 z-20">
      <div className="flex items-center gap-3">
        <span className="text-sm text-surface-700">Channel:</span>
        <span className="text-sm font-medium text-surface-900">
          {connected ? (connection.channel_title || 'YouTube Channel') : 'Not connected'}
        </span>
        {connected ? (
          <span className="flex items-center gap-1 text-xs text-emerald-400">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <Wifi size={14} /> Connected
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs text-surface-600">
            <WifiOff size={14} /> Disconnected
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="text-sm text-surface-700">{user?.full_name || user?.email}</span>
        <div className="w-8 h-8 rounded-full gradient-brand flex items-center justify-center">
          <UserCircle size={20} className="text-white/80" />
        </div>
      </div>
    </header>
  );
}
