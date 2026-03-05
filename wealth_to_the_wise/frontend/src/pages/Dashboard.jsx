import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { SkeletonStatCards, SkeletonVideoList } from '../components/Skeleton';
import { FadeIn } from '../components/Motion';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import {
  Film, Upload, CalendarClock, CheckCircle2, Clock, AlertTriangle,
  Sparkles, RefreshCw, TrendingUp, ArrowRight, DollarSign,
  Search, Image as ImageIcon, Eye, Mic,
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

/* Animated counter */
function AnimatedNumber({ value, duration = 0.8 }) {
  return (
    <motion.span
      key={value}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {value}
    </motion.span>
  );
}

/* ── Bento tile — the building block ── */
function BentoTile({ to, icon: Icon, iconColor, gradient, label, value, desc, delay = 0, className = '' }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: [0.25, 0.1, 0.25, 1] }}
    >
      <Link to={to} className={`bento-tile group block card p-5 h-full transition-all duration-200 hover:border-[var(--border-strong)] ${className}`}>
        <div className="flex items-center justify-between mb-3">
          <div className={`w-9 h-9 rounded-[10px] bg-gradient-to-br ${gradient} flex items-center justify-center`}>
            <Icon size={17} className={iconColor} />
          </div>
          <ArrowRight size={14} className="text-surface-500 opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all duration-200" />
        </div>
        {value !== undefined && (
          <p className="text-[28px] font-bold text-white tabular-nums tracking-tight leading-none mb-1">
            <AnimatedNumber value={value} />
          </p>
        )}
        <p className="text-[13px] font-medium text-surface-800">{label}</p>
        {desc && <p className="text-[11px] text-surface-500 mt-0.5">{desc}</p>}
      </Link>
    </motion.div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
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
      setActivity(historyRes.data.slice(0, 6));
    } catch {
      // gracefully show empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const firstName = (user?.full_name || user?.email || '').split(' ')[0] || 'there';
  const greeting = new Date().getHours() < 12 ? 'Good morning' : new Date().getHours() < 18 ? 'Good afternoon' : 'Good evening';

  const monthlyUsed = stats?.monthly_used ?? 0;
  const monthlyLimit = stats?.monthly_limit ?? 1;
  const plan = stats?.plan ?? 'free';
  const usagePct = Math.min(100, Math.round((monthlyUsed / monthlyLimit) * 100));

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto space-y-5">
        <div className="space-y-2"><div className="skeleton h-7 w-64" /><div className="skeleton h-3 w-48" /></div>
        <SkeletonStatCards />
        <div className="skeleton h-16 w-full" />
        <SkeletonVideoList />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <PageHeader
        title={`${greeting}, ${firstName}`}
        subtitle="Pipeline overview"
        action={
          <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
            onClick={fetchData}
            className="p-2 rounded-[8px] text-surface-600 hover:text-surface-800 hover:bg-white/[0.04] transition-colors duration-150"
            title="Refresh">
            <RefreshCw size={16} />
          </motion.button>
        }
      />

      {/* ── Bento Grid ── */}
      <div className="bento-grid">
        {/* Row 1: Three stat tiles */}
        <BentoTile
          to="/videos" icon={Film} iconColor="text-indigo-400"
          gradient="from-indigo-500/15 to-indigo-500/5"
          label="Total Generated" value={stats?.total_generated ?? 0}
          desc="All time" delay={0.05}
        />
        <BentoTile
          to="/videos" icon={Upload} iconColor="text-emerald-400"
          gradient="from-emerald-500/15 to-emerald-500/5"
          label="Posted" value={stats?.total_posted ?? 0}
          desc="Uploaded to YouTube" delay={0.1}
        />
        <BentoTile
          to="/schedule" icon={CalendarClock} iconColor="text-amber-400"
          gradient="from-amber-500/15 to-amber-500/5"
          label="In Progress" value={stats?.total_pending ?? 0}
          desc="Generating now" delay={0.15}
        />

        {/* Row 2: Quota (wide) + Quick links */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
          className="bento-wide"
        >
          <div className="card p-5 h-full">
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
            <div className="w-full bg-surface-300/50 rounded-full h-[4px] overflow-hidden">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${monthlyLimit >= 999_999 ? 3 : usagePct}%` }}
                transition={{ duration: 0.8, ease: [0.25, 0.1, 0.25, 1], delay: 0.4 }}
                className={`h-[4px] rounded-full ${usagePct >= 90 ? 'bg-red-500' : usagePct >= 70 ? 'bg-amber-500' : 'bg-brand-500'}`}
              />
            </div>
            {/* Quick nav row */}
            <div className="flex gap-2 mt-5 flex-wrap">
              {[
                { to: '/revenue', label: 'Revenue', icon: DollarSign },
                { to: '/niche', label: 'Niche Intel', icon: Search },
                { to: '/thumbnails', label: 'Thumbnails', icon: ImageIcon },
                { to: '/competitors', label: 'Competitors', icon: Eye },
                { to: '/voices', label: 'Voices', icon: Mic },
              ].map(({ to, label, icon: QIcon }) => (
                <Link key={to} to={to}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-[8px] bg-white/[0.03] hover:bg-white/[0.06] text-surface-600 hover:text-surface-800 text-[11px] font-medium transition-all duration-150">
                  <QIcon size={12} /> {label}
                </Link>
              ))}
            </div>
          </div>
        </motion.div>

        {/* Row 3: Recent activity (full width) */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
          className="bento-full"
        >
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[12px] font-semibold text-surface-600 uppercase tracking-[0.08em]">
                Recent Activity
              </h2>
              <Link to="/videos" className="text-[11px] text-surface-500 hover:text-brand-400 transition-colors flex items-center gap-1">
                View all <ArrowRight size={10} />
              </Link>
            </div>
            {activity.length === 0 ? (
              <EmptyState
                icon={Sparkles}
                title="No videos yet"
                description="Head to the Videos page to generate your first one."
                action={
                  <Link to="/videos" className="btn-primary text-[13px]">
                    Create First Video <ArrowRight size={14} />
                  </Link>
                }
              />
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
                      transition={{ delay: 0.3 + i * 0.03, duration: 0.2 }}
                      className="flex items-center gap-4 px-5 py-3.5 hover:bg-white/[0.02] transition-colors duration-150"
                    >
                      <div className="w-8 h-8 rounded-[8px] bg-surface-200 flex items-center justify-center shrink-0">
                        <Icon size={14} className={cfg.color} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[13px] font-medium text-surface-900 truncate">{item.title}</p>
                        <p className="text-[11px] text-surface-600 mt-0.5">{timeSince(item.created_at)}</p>
                      </div>
                      <span className={`badge ${
                        item.status === 'posted' ? 'badge-posted' :
                        item.status === 'failed' ? 'badge-failed' :
                        item.status === 'generating' ? 'badge-generating' : 'badge-pending'
                      }`}>{item.status}</span>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
