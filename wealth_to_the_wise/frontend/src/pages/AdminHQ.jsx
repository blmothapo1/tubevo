import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import {
  Shield,
  Users,
  UserPlus,
  Mail,
  Film,
  Zap,
  AlertTriangle,
  TrendingUp,
  Clock,
  RefreshCw,
  CheckCircle2,
  Upload,
  XCircle,
  ArrowRight,
} from 'lucide-react';

// ── Helpers ─────────────────────────────────────────────────────────

function timeSince(dateStr) {
  if (!dateStr) return '';
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function formatDuration(secs) {
  if (secs == null) return '—';
  if (secs < 60) return `${Math.round(secs)}s`;
  return `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s`;
}

const EVENT_CONFIG = {
  user_signup:     { icon: UserPlus,      color: 'text-brand-400',   bg: 'bg-brand-500/10',   label: 'User signed up' },
  video_started:   { icon: Film,          color: 'text-amber-400',   bg: 'bg-amber-500/10',   label: 'Video started' },
  video_completed: { icon: CheckCircle2,  color: 'text-emerald-400', bg: 'bg-emerald-500/10', label: 'Video completed' },
  video_failed:    { icon: AlertTriangle, color: 'text-red-400',     bg: 'bg-red-500/10',     label: 'Video failed' },
  upload_success:  { icon: Upload,        color: 'text-emerald-400', bg: 'bg-emerald-500/10', label: 'Upload success' },
  upload_failed:   { icon: XCircle,       color: 'text-red-400',     bg: 'bg-red-500/10',     label: 'Upload failed' },
};


// ── Component ───────────────────────────────────────────────────────

export default function AdminHQ() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchOverview = useCallback(async () => {
    try {
      setError(null);
      const { data: res } = await api.get('/api/admin/overview');
      setData(res);
    } catch (err) {
      setError('Failed to load admin overview.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);

  const kpis = data?.kpis;
  const activity = data?.activity ?? [];

  const kpiCards = kpis ? [
    { label: 'Total Users',       value: kpis.total_users,        icon: Users,          gradient: 'from-brand-500/15 to-brand-500/5',   iconColor: 'text-brand-400' },
    { label: 'New Users (24h)',    value: kpis.new_users_24h,      icon: UserPlus,       gradient: 'from-indigo-500/15 to-indigo-500/5', iconColor: 'text-indigo-400' },
    { label: 'Waitlist Signups',   value: kpis.total_waitlist,     icon: Mail,           gradient: 'from-violet-500/15 to-violet-500/5', iconColor: 'text-violet-400' },
    { label: 'Total Videos',       value: kpis.total_videos,       icon: Film,           gradient: 'from-cyan-500/15 to-cyan-500/5',     iconColor: 'text-cyan-400' },
    { label: 'Videos (24h)',       value: kpis.videos_24h,         icon: Zap,            gradient: 'from-amber-500/15 to-amber-500/5',   iconColor: 'text-amber-400' },
    { label: 'Failed (24h)',       value: kpis.videos_failed_24h,  icon: AlertTriangle,  gradient: 'from-red-500/15 to-red-500/5',       iconColor: 'text-red-400' },
    { label: 'Success Rate',       value: `${kpis.success_rate}%`, icon: TrendingUp,     gradient: 'from-emerald-500/15 to-emerald-500/5', iconColor: 'text-emerald-400' },
    { label: 'Avg Build Time',     value: formatDuration(kpis.avg_generation_secs), icon: Clock, gradient: 'from-surface-400/15 to-surface-400/5', iconColor: 'text-surface-700' },
  ] : [];

  return (
    <div className="min-h-screen bg-surface-50 flex flex-col">
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <header className="h-[60px] glass sticky top-0 z-20 flex items-center justify-between mobile-content-padding sm:px-8 safe-area-inset">
        <div className="flex items-center gap-3">
          <span className="text-[18px] sm:text-[20px] font-semibold text-white" style={{ fontFamily: "'Poppins', sans-serif" }}>
            Tubevo
          </span>
          <span className="text-[11px] font-medium tracking-wide uppercase px-2 py-0.5 rounded-[5px] bg-brand-500/15 text-brand-400">
            Admin
          </span>
        </div>

        <div className="flex items-center gap-3">
          <motion.button
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.94 }}
            onClick={() => { setLoading(true); fetchOverview(); }}
            className="p-2 rounded-[8px] text-surface-600 hover:text-surface-800 hover:bg-white/[0.04] transition-colors duration-150"
            title="Refresh"
          >
            <RefreshCw size={16} />
          </motion.button>
          <div className="flex items-center gap-2 text-[13px] text-surface-600">
            <Shield size={14} className="text-brand-400" />
            <span className="hidden sm:inline">{user?.email}</span>
          </div>
        </div>
      </header>

      {/* ── Content ─────────────────────────────────────────────────── */}
      <main className="flex-1 w-full max-w-6xl mx-auto mobile-content-padding sm:px-8 sm:py-8 lg:px-10">

        {/* Page title */}
        <FadeIn>
          <div className="mb-8">
            <h1 className="text-[22px] sm:text-[26px] font-semibold text-white tracking-tight">
              Admin HQ
            </h1>
            <p className="text-[12px] text-surface-600 mt-1.5 uppercase tracking-[0.08em] font-medium">
              Platform overview
            </p>
          </div>
        </FadeIn>

        {/* Quick nav */}
        <FadeIn delay={0.05}>
          <div className="flex gap-2 mb-6">
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate('/admin/users')}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[8px] bg-brand-500/10 text-brand-400 text-[12px] font-medium hover:bg-brand-500/20 transition-colors duration-150"
            >
              <Users size={14} />
              Manage Users
              <ArrowRight size={12} />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate('/admin/videos')}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[8px] bg-cyan-500/10 text-cyan-400 text-[12px] font-medium hover:bg-cyan-500/20 transition-colors duration-150"
            >
              <Film size={14} />
              Manage Videos
              <ArrowRight size={12} />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate('/admin/errors')}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[8px] bg-red-500/10 text-red-400 text-[12px] font-medium hover:bg-red-500/20 transition-colors duration-150"
            >
              <AlertTriangle size={14} />
              Errors
              <ArrowRight size={12} />
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate('/admin/waitlist')}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[8px] bg-violet-500/10 text-violet-400 text-[12px] font-medium hover:bg-violet-500/20 transition-colors duration-150"
            >
              <Mail size={14} />
              Waitlist
              <ArrowRight size={12} />
            </motion.button>
          </div>
        </FadeIn>

        {/* Error state */}
        {error && (
          <FadeIn>
            <div className="card px-5 py-4 mb-6 border-l-[3px] border-l-red-500">
              <p className="text-[13px] text-red-400">{error}</p>
            </div>
          </FadeIn>
        )}

        {/* Loading skeleton */}
        {loading && !data && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="card p-5 space-y-3">
                  <div className="skeleton h-3 w-20" />
                  <div className="skeleton h-7 w-14" />
                </div>
              ))}
            </div>
            <div className="card p-4 space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex gap-3 items-center">
                  <div className="skeleton w-8 h-8 rounded-[8px]" />
                  <div className="flex-1 space-y-1.5">
                    <div className="skeleton h-3 w-2/3" />
                    <div className="skeleton h-2 w-1/3" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── KPI Cards ────────────────────────────────────────────── */}
        {data && (
          <>
            <StaggerContainer className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
              {kpiCards.map(({ label, value, icon: Icon, gradient, iconColor }) => (
                <StaggerItem key={label}>
                  <div className="card p-5">
                    <div className="flex items-center gap-3 mb-3">
                      <div className={`w-8 h-8 rounded-[8px] bg-gradient-to-br ${gradient} flex items-center justify-center`}>
                        <Icon size={15} className={iconColor} />
                      </div>
                    </div>
                    <p className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em]">{label}</p>
                    <p className="text-[26px] font-bold text-white mt-1 tabular-nums tracking-tight leading-none">{value}</p>
                  </div>
                </StaggerItem>
              ))}
            </StaggerContainer>

            {/* ── Activity Feed ──────────────────────────────────────── */}
            <FadeIn delay={0.2}>
              <h2 className="text-[12px] font-semibold text-surface-600 uppercase tracking-[0.08em] mb-4">
                Recent Activity
              </h2>

              {activity.length === 0 ? (
                <div className="card px-6 py-14 text-center">
                  <p className="text-[14px] text-surface-700">No events recorded yet.</p>
                  <p className="text-[12px] text-surface-600 mt-1">Events will appear here as users interact with the platform.</p>
                </div>
              ) : (
                <div className="card overflow-hidden divide-y divide-white/[0.03]">
                  {activity.map((item, i) => {
                    const cfg = EVENT_CONFIG[item.type] || { icon: Zap, color: 'text-surface-600', bg: 'bg-surface-200', label: item.type };
                    const Icon = cfg.icon;
                    const meta = item.metadata || {};

                    // Build a one-liner description
                    let desc = cfg.label;
                    if (item.user_email) desc += ` · ${item.user_email}`;
                    if (meta.topic) desc += ` — "${meta.topic}"`;
                    if (meta.title) desc += ` — "${meta.title}"`;
                    if (meta.error) desc += ` — ${meta.error.slice(0, 80)}`;
                    if (meta.youtube_id) desc += ` (${meta.youtube_id})`;

                    return (
                      <motion.div
                        key={item.id}
                        initial={{ opacity: 0, x: -4 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.02, duration: 0.15 }}
                        className="flex items-center gap-3 px-4 py-3 hover:bg-white/[0.015] transition-colors duration-100"
                      >
                        <div className={`w-7 h-7 rounded-[6px] ${cfg.bg} flex items-center justify-center shrink-0`}>
                          <Icon size={13} className={cfg.color} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-[13px] text-surface-800 truncate">{desc}</p>
                        </div>
                        <span className="text-[11px] text-surface-600 shrink-0 tabular-nums">
                          {timeSince(item.created_at)}
                        </span>
                      </motion.div>
                    );
                  })}
                </div>
              )}
            </FadeIn>
          </>
        )}
      </main>
    </div>
  );
}
