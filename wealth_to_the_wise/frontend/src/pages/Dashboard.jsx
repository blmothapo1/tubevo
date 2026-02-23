import { useState, useEffect, useCallback } from 'react';
import api from '../lib/api';
import Spinner from '../components/Spinner';
import {
  Film,
  Upload,
  CalendarClock,
  Play,
  Pause,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Sparkles,
  RefreshCw,
} from 'lucide-react';

const statusIcons = {
  posted: { icon: CheckCircle2, color: 'text-emerald-400' },
  completed: { icon: CheckCircle2, color: 'text-emerald-400' },
  generating: { icon: Film, color: 'text-brand-400' },
  pending: { icon: Clock, color: 'text-amber-400' },
  failed: { icon: AlertTriangle, color: 'text-red-400' },
};

function timeSince(dateStr) {
  if (!dateStr) return '';
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export default function Dashboard() {
  const [automationOn, setAutomationOn] = useState(false);
  const [stats, setStats] = useState(null);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [genMsg, setGenMsg] = useState('');

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, historyRes] = await Promise.all([
        api.get('/api/videos/stats'),
        api.get('/api/videos/history'),
      ]);
      setStats(statsRes.data);
      setActivity(historyRes.data.slice(0, 8));
    } catch {
      // gracefully show empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleQuickGenerate() {
    setGenerating(true);
    setGenMsg('');
    try {
      const { data } = await api.post('/api/videos/generate', { topic: '' });
      setGenMsg(data.message || 'Video queued!');
      fetchData();
    } catch (err) {
      if (err.response?.status === 422) {
        setGenMsg('Enter a topic on the Videos page to generate.');
      } else {
        setGenMsg(err.response?.data?.detail || 'Generation failed.');
      }
    } finally {
      setGenerating(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner className="w-8 h-8" />
      </div>
    );
  }

  const statCards = [
    { label: 'Total Generated', value: stats?.total_generated ?? 0, icon: Film, color: 'text-brand-400', border: 'border-l-brand-500' },
    { label: 'Posted', value: stats?.total_posted ?? 0, icon: Upload, color: 'text-emerald-400', border: 'border-l-emerald-500' },
    { label: 'In Progress', value: stats?.total_pending ?? 0, icon: CalendarClock, color: 'text-amber-400', border: 'border-l-amber-500' },
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Dashboard</h1>
          <p className="text-sm text-surface-700 mt-1">Overview of your automation pipeline</p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchData}
            className="p-2.5 rounded-lg text-surface-600 hover:text-surface-800 hover:bg-surface-200 transition-colors"
            title="Refresh"
          >
            <RefreshCw size={16} />
          </button>
          <button
            onClick={() => setAutomationOn(!automationOn)}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
              automationOn
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25 shadow-[0_0_15px_rgba(52,211,153,0.15)]'
                : 'bg-surface-200 text-surface-700 border border-surface-300 hover:bg-surface-300'
            }`}
          >
            {automationOn ? <Pause size={16} /> : <Play size={16} />}
            {automationOn ? 'Automation Running' : 'Start Automation'}
          </button>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {statCards.map(({ label, value, icon: Icon, color, border }) => (
          <div
            key={label}
            className={`bg-surface-100 border border-surface-300 border-l-2 ${border} rounded-xl p-5 flex items-center gap-4`}
          >
            <div className="w-10 h-10 rounded-lg bg-surface-200 flex items-center justify-center">
              <Icon size={20} className={color} />
            </div>
            <div>
              <p className="text-xs text-surface-600 uppercase tracking-wider">{label}</p>
              <p className="text-lg font-semibold text-white mt-0.5">{value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Automation Status Banner */}
      {automationOn && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-5 py-4 flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <p className="text-sm text-emerald-300">
            Pipeline is active — videos are being generated and queued automatically.
          </p>
        </div>
      )}

      {/* Quick Generate */}
      {genMsg && (
        <div className="bg-brand-500/10 border border-brand-500/20 text-brand-300 text-sm px-4 py-2.5 rounded-lg">
          {genMsg}
        </div>
      )}

      {/* Recent Activity */}
      <div>
        <h2 className="text-sm font-medium text-surface-700 uppercase tracking-wider mb-4">
          Recent Activity
        </h2>
        {activity.length === 0 ? (
          <div className="bg-surface-100 border border-surface-300 rounded-xl px-5 py-12 text-center">
            <Sparkles size={32} className="text-surface-500 mx-auto mb-3" />
            <p className="text-sm text-surface-600">
              No videos yet. Head to the{' '}
              <a href="/videos" className="text-brand-400 hover:text-brand-300 underline">
                Videos
              </a>{' '}
              page to generate your first one!
            </p>
          </div>
        ) : (
          <div className="bg-surface-100 border border-surface-300 rounded-xl divide-y divide-surface-300">
            {activity.map((item) => {
              const cfg = statusIcons[item.status] || statusIcons.pending;
              const Icon = cfg.icon;

              return (
                <div key={item.id} className="flex items-center gap-4 px-5 py-4">
                  <div className="w-8 h-8 rounded-lg bg-surface-200 flex items-center justify-center shrink-0">
                    <Icon size={16} className={cfg.color} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-surface-900 truncate">{item.title}</p>
                    <p className="text-xs text-surface-600 mt-0.5">{timeSince(item.created_at)}</p>
                  </div>
                  <span
                    className={`text-xs font-medium px-2.5 py-1 rounded-full capitalize ${
                      item.status === 'posted'
                        ? 'bg-emerald-500/15 text-emerald-400'
                        : item.status === 'failed'
                        ? 'bg-red-500/15 text-red-400'
                        : item.status === 'generating'
                        ? 'bg-brand-500/15 text-brand-400'
                        : 'bg-amber-500/15 text-amber-400'
                    }`}
                  >
                    {item.status}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
