import { useAuth } from '../contexts/AuthContext';
import { Wifi, WifiOff, UserCircle } from 'lucide-react';

export default function Topbar() {
  const { user } = useAuth();
  const connected = false; // Will be driven by YouTube OAuth later

  return (
    <header className="h-16 border-b border-surface-300 bg-surface-100/80 backdrop-blur-sm flex items-center justify-between px-6 sticky top-0 z-20">
      <div className="flex items-center gap-3">
        <span className="text-sm text-surface-700">Channel:</span>
        <span className="text-sm font-medium text-surface-900">
          {connected ? 'Wealth to the Wise' : 'Not connected'}
        </span>
        {connected ? (
          <span className="flex items-center gap-1 text-xs text-emerald-400">
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
        <div className="w-8 h-8 rounded-full bg-brand-600/20 flex items-center justify-center">
          <UserCircle size={20} className="text-brand-400" />
        </div>
      </div>
    </header>
  );
}
