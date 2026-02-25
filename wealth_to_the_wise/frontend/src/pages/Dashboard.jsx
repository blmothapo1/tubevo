import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { SkeletonStatCards, SkeletonVideoList } from '../components/Skeleton';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
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
  TrendingUp,
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
  const { user } = useAuth();
  const [automationOn, setAutomationOn] = useState(false);
  const [stats, setStats] = useState(null);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);

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

  const firstName = (user?.full_name || user?.email || '').split(' ')[0] || 'there';
  const greeting = new Date().getHours() < 12 ? 'Good morning' : new Date().getHours() < 18 ? 'Good afternoon' : 'Good evening';

  const statCards = [
    { label: 'Total Generated', value: stats?.total_generated ?? 0, icon: Film, gradient: 'from-indigo-500/15 to-indigo-500/5', iconColor: 'text-indigo-400' },
    { label: 'Posted', value: stats?.total_posted ?? 0, icon: Upload, gradient: 'from-emerald-500/15 to-emerald-500/5', iconColor: 'text-emerald-400' },
    { label: 'In Progress', value: stats?.total_pending ?? 0, icon: CalendarClock, gradient: 'from-amber-500/15 to-amber-500/5', iconColor: 'text-amber-400' },
  ];

  const monthlyUsed = stats?.monthly_used ?? 0;
  const monthlyLimit = stats?.monthly_limit ?? 1;
  const plan = stats?.plan ?? 'free';
  const usagePct = Math.min(100, Math.round((monthlyUsed / monthlyLimit) * 100));

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto space-y-6 sm:space-y-8">
        <div className="space-y-2">
          <div className="skeleton h-8 w-64" />
          <div className="skeleton h-4 w-48" />
        </div>
        <SkeletonStatCards />
        <div className="skeleton h-20 w-full rounded-2xl" />
        <SkeletonVideoList />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6 sm:space-y-8">
      {/* Header with personalized greeting */}
      <FadeIn>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-semibold text-white tracking-tight">
              {greeting}, {firstName} ✨
            </h1>
            <p className="text-sm text-surface-600 mt-1.5">Here's what's happening with your pipeline</p>
          </div>

          <div className="flex items-center gap-3">
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={fetchData}
              className="p-2.5 rounded-xl text-surface-600 hover:text-surface-800 hover:bg-surface-200/80 transition-all duration-200"
              title="Refresh"
            >
              <RefreshCw size={16} />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setAutomationOn(!automationOn)}
              className={`flex items-center gap-2.5 px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 ${
                automationOn
                  ? 'bg-emerald-500/12 text-emerald-400 border border-emerald-500/25 shadow-[0_0_20px_rgba(52,211,153,0.1)]'
                  : 'bg-surface-200/80 text-surface-700 border border-surface-300 hover:bg-surface-300/80'
              }`}
            >
              {automationOn ? <Pause size={16} /> : <Play size={16} />}
              {automationOn ? 'Running' : 'Start Automation'}
            </motion.button>
          </div>
        </div>
      </FadeIn>

      {/* Stats Row */}
      <StaggerContainer className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-5 lg:gap-6">
        {statCards.map(({ label, value, icon: Icon, gradient, iconColor }) => (
          <StaggerItem key={label}>
            <motion.div
              whileHover={{ y: -2, transition: { duration: 0.2 } }}
              className="card-elevated p-5 sm:p-6 flex items-center gap-4"
            >
              <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center`}>
                <Icon size={22} className={iconColor} />
              </div>
              <div>
                <p className="text-xs text-surface-600 font-medium uppercase tracking-wider">{label}</p>
                <p className="text-2xl font-bold text-white mt-0.5 tracking-tight">{value}</p>
              </div>
            </motion.div>
          </StaggerItem>
        ))}
      </StaggerContainer>

      {/* Monthly Quota */}
      <FadeIn delay={0.2}>
        <div className="card p-5 sm:p-6">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <TrendingUp size={14} className="text-surface-600" />
              <span className="text-xs text-surface-600 font-medium uppercase tracking-wider">
                Monthly Quota · {plan.charAt(0).toUpperCase() + plan.slice(1)} Plan
              </span>
            </div>
            <span className="text-sm font-semibold text-white">
              {monthlyUsed} / {monthlyLimit >= 999_999 ? '∞' : monthlyLimit}
            </span>
          </div>
          <div className="w-full bg-surface-300/50 rounded-full h-2.5 overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${monthlyLimit >= 999_999 ? 3 : usagePct}%` }}
              transition={{ duration: 0.8, ease: [0.25, 0.1, 0.25, 1], delay: 0.3 }}
              className={`h-2.5 rounded-full ${usagePct >= 90 ? 'bg-red-500' : usagePct >= 70 ? 'bg-amber-500' : 'gradient-brand'}`}
            />
          </div>
        </div>
      </FadeIn>

      {/* Automation Status Banner */}
      {automationOn && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          className="bg-emerald-500/8 border border-emerald-500/15 rounded-2xl px-6 py-4 flex items-center gap-3"
        >
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-soft-pulse" />
          <p className="text-sm text-emerald-300">
            Pipeline is active — videos are being generated and queued automatically.
          </p>
        </motion.div>
      )}

      {/* Recent Activity */}
      <FadeIn delay={0.3}>
        <div>
          <h2 className="text-xs font-medium text-surface-600 uppercase tracking-wider mb-4 sm:mb-5">
            Recent Activity
          </h2>
          {activity.length === 0 ? (
            <div className="card px-5 py-12 sm:px-6 sm:py-16 text-center">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-brand-500/15 to-brand-500/5 flex items-center justify-center mx-auto mb-4">
                <Sparkles size={24} className="text-brand-400" />
              </div>
              <p className="text-sm font-medium text-surface-800 mb-1">No videos yet</p>
              <p className="text-sm text-surface-600">
                Head to the{' '}
                <a href="/videos" className="text-brand-400 hover:text-brand-300 font-medium transition-colors">
                  Videos
                </a>{' '}
                page to generate your first one!
              </p>
            </div>
          ) : (
            <div className="card divide-y divide-surface-300/50 overflow-hidden">
              {activity.map((item, i) => {
                const cfg = statusIcons[item.status] || statusIcons.pending;
                const Icon = cfg.icon;

                return (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.04, duration: 0.3 }}
                    className="flex items-center gap-3 sm:gap-4 px-4 py-3.5 sm:px-6 sm:py-4 hover:bg-surface-200/30 transition-colors duration-200"
                  >
                    <div className="w-9 h-9 rounded-xl bg-surface-200/80 flex items-center justify-center shrink-0">
                      <Icon size={16} className={cfg.color} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-surface-900 truncate">{item.title}</p>
                      <p className="text-xs text-surface-600 mt-0.5">{timeSince(item.created_at)}</p>
                    </div>
                    <span
                      className={`text-xs font-medium px-3 py-1 rounded-full capitalize ${
                        item.status === 'posted'
                          ? 'bg-emerald-500/10 text-emerald-400'
                          : item.status === 'failed'
                          ? 'bg-red-500/10 text-red-400'
                          : item.status === 'generating'
                          ? 'bg-brand-500/10 text-brand-400'
                          : 'bg-amber-500/10 text-amber-400'
                      }`}
                    >
                      {item.status}
                    </span>
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>
      </FadeIn>
    </div>
  );
}
