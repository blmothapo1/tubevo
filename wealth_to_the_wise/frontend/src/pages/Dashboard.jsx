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
      <div className="max-w-5xl mx-auto space-y-5 sm:space-y-6">
        <div className="space-y-2">
          <div className="skeleton h-7 w-64" />
          <div className="skeleton h-3 w-48" />
        </div>
        <SkeletonStatCards />
        <div className="skeleton h-16 w-full" />
        <SkeletonVideoList />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-7">
      {/* Header with personalized greeting */}
      <FadeIn>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-[20px] sm:text-[24px] font-semibold text-white tracking-tight">
              {greeting}, {firstName}
            </h1>
            <p className="text-[12px] text-surface-600 mt-2 uppercase tracking-[0.08em] font-medium">Pipeline overview</p>
          </div>

          <div className="flex items-center gap-2">
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              onClick={fetchData}
              className="p-2 rounded-[8px] text-surface-600 hover:text-surface-800 hover:bg-white/[0.04] transition-colors duration-150"
              title="Refresh"
            >
              <RefreshCw size={16} />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              onClick={() => setAutomationOn(!automationOn)}
              className={`flex items-center gap-2 px-4 py-2 rounded-[8px] text-[12px] font-medium tracking-wide uppercase transition-all duration-150 ${
                automationOn
                  ? 'bg-emerald-500/10 text-emerald-400'
                  : 'bg-surface-200 text-surface-700 hover:bg-surface-300'
              }`}
            >
              {automationOn ? <Pause size={14} /> : <Play size={14} />}
              {automationOn ? 'Running' : 'Start'}
            </motion.button>
          </div>
        </div>
      </FadeIn>

      {/* Stats Row */}
      <StaggerContainer className="grid grid-cols-1 sm:grid-cols-3 gap-5">
        {statCards.map(({ label, value, icon: Icon, gradient, iconColor }) => (
          <StaggerItem key={label}>
            <div className="card p-5 flex items-center gap-4 border-l-[3px] border-l-brand-500">
              <div className={`w-10 h-10 rounded-[10px] bg-gradient-to-br ${gradient} flex items-center justify-center`}>
                <Icon size={18} className={iconColor} />
              </div>
              <div>
                <p className="text-[12px] text-surface-600 font-medium uppercase tracking-[0.08em]">{label}</p>
                <p className="text-[32px] font-bold text-white mt-0.5 tabular-nums tracking-tight leading-none">{value}</p>
              </div>
            </div>
          </StaggerItem>
        ))}
      </StaggerContainer>

      {/* Monthly Quota */}
      <FadeIn delay={0.2}>
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <TrendingUp size={14} className="text-surface-600" />
              <span className="text-[12px] text-surface-600 font-medium uppercase tracking-[0.08em]">
                Monthly Quota · {plan.charAt(0).toUpperCase() + plan.slice(1)}
              </span>
            </div>
            <span className="text-[13px] font-semibold text-white tabular-nums">
              {monthlyUsed} / {monthlyLimit >= 999_999 ? '∞' : monthlyLimit}
            </span>
          </div>
          <div className="w-full bg-surface-300/50 rounded-full h-[3px] overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${monthlyLimit >= 999_999 ? 3 : usagePct}%` }}
              transition={{ duration: 0.6, ease: [0.25, 0.1, 0.25, 1], delay: 0.3 }}
              className={`h-[3px] rounded-full ${usagePct >= 90 ? 'bg-red-500' : usagePct >= 70 ? 'bg-amber-500' : 'bg-brand-500'}`}
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
          className="bg-emerald-500/6 rounded-[10px] px-5 py-3 flex items-center gap-2.5"
        >
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-soft-pulse" />
          <p className="text-[13px] text-emerald-300">
            Pipeline active — videos are being generated and queued automatically.
          </p>
        </motion.div>
      )}

      {/* Recent Activity */}
      <FadeIn delay={0.3}>
        <div>
          <h2 className="text-[12px] font-semibold text-surface-600 uppercase tracking-[0.08em] mb-5">
            Recent Activity
          </h2>
          {activity.length === 0 ? (
            <div className="card px-6 py-14 text-center">
              <div className="w-12 h-12 rounded-[10px] bg-brand-500/10 flex items-center justify-center mx-auto mb-4">
                <Sparkles size={20} className="text-brand-400" />
              </div>
              <p className="text-[14px] font-medium text-surface-800 mb-1.5">No videos yet</p>
              <p className="text-[13px] text-surface-600">
                Head to the{' '}
                <a href="/videos" className="text-brand-400 hover:text-brand-300 font-medium transition-colors">
                  Videos
                </a>{' '}
                page to generate your first one.
              </p>
            </div>
          ) : (
            <div className="card overflow-hidden">
              {activity.map((item, i) => {
                const cfg = statusIcons[item.status] || statusIcons.pending;
                const Icon = cfg.icon;

                return (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.03, duration: 0.2 }}
                    className="flex items-center gap-4 px-5 py-4 hover:bg-white/[0.02] transition-colors duration-150"
                  >
                    <div className="w-8 h-8 rounded-[8px] bg-surface-200 flex items-center justify-center shrink-0">
                      <Icon size={14} className={cfg.color} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[14px] font-medium text-surface-900 truncate">{item.title}</p>
                      <p className="text-[11px] text-surface-600 mt-1">{timeSince(item.created_at)}</p>
                    </div>
                    <span
                      className={`badge ${
                        item.status === 'posted'
                          ? 'badge-posted'
                          : item.status === 'failed'
                          ? 'badge-failed'
                          : item.status === 'generating'
                          ? 'badge-generating'
                          : 'badge-pending'
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
