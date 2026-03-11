import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Radar, Zap, Rocket, X, RefreshCw, Play, Bot,
  TrendingUp, AlertTriangle, CheckCircle, Clock, Flame,
  Settings as SettingsIcon, ChevronDown, ChevronUp,
  BarChart3, Target, Loader2, Sparkles, Check
} from 'lucide-react';
import api from '../lib/api';
import { useToast } from '../contexts/ToastContext';

/* ── Available niches (matches Onboarding) ── */
const ALL_NICHES = [
  'Personal Finance', 'Investing / Stocks', 'Business & Entrepreneurship',
  'Self-Improvement', 'Psychology', 'Productivity', 'Tech & Innovation',
  'True Crime', 'Horror Stories', 'Mystery & Conspiracy',
  'History', 'Science & Space', 'Fitness & Health',
  'Luxury & Wealth', 'Geography & World Facts',
];

const ease = [0.25, 0.1, 0.25, 1];

/* ── Inline niche quick-setup ── */
function NicheSetup({ onComplete }) {
  const toast = useToast();
  const [selected, setSelected] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const toggle = (niche) =>
    setSelected(prev =>
      prev.includes(niche) ? prev.filter(n => n !== niche) : prev.length < 5 ? [...prev, niche] : prev
    );

  const handleSave = async () => {
    if (selected.length === 0) return;
    setSaving(true);
    setError('');
    try {
      await api.put('/api/videos/channel-preferences', {
        niches: selected,
        tone_style: 'confident, direct, no-fluff educator',
        target_audience: 'general audience',
        channel_goal: 'growth',
        posting_frequency: 'weekly',
      });
      toast.success('Niches saved!');
      onComplete();
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to save niches';
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease }}
      className="card bento-tile p-8 max-w-2xl mx-auto"
    >
      <div className="text-center mb-6">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl surface-inset mb-4">
          <Sparkles className="w-7 h-7 text-[var(--color-brand-500)]" />
        </div>
        <h2 className="text-lg font-bold text-[var(--color-surface-900)]">Pick Your Niches</h2>
        <p className="text-sm text-[var(--color-surface-600)] mt-1 max-w-md mx-auto">
          Choose up to 5 topics the Trend Radar should monitor for viral opportunities.
        </p>
      </div>

      <div className="flex flex-wrap gap-2 justify-center mb-6">
        {ALL_NICHES.map(niche => {
          const active = selected.includes(niche);
          return (
            <button
              key={niche}
              onClick={() => toggle(niche)}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-[var(--radius-md)] border transition-all duration-150 ${
                active
                  ? 'bg-[color-mix(in_srgb,var(--color-brand-500)_12%,transparent)] text-[var(--color-brand-500)] border-[color-mix(in_srgb,var(--color-brand-500)_25%,transparent)]'
                  : 'text-[var(--color-surface-600)] border-[var(--border-subtle)] hover:border-[var(--border-hover)] hover:text-[var(--color-surface-800)]'
              }`}
            >
              {active && <Check className="w-3 h-3" />}
              {niche}
            </button>
          );
        })}
      </div>

      <p className="text-center text-xs text-[var(--color-surface-600)] mb-4">
        {selected.length}/5 selected {selected.length === 0 && '— pick at least one'}
      </p>

      {error && (
        <p className="text-center text-xs text-red-400 mb-3">{error}</p>
      )}

      <div className="flex justify-center">
        <button
          onClick={handleSave}
          disabled={selected.length === 0 || saving}
          className="btn-primary"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Radar className="w-4 h-4" />}
          {saving ? 'Saving…' : 'Activate Trend Radar'}
        </button>
      </div>
    </motion.div>
  );
}

/* ── Confidence badge ── */
function ConfidenceBadge({ score }) {
  const color =
    score >= 80 ? 'bg-emerald-500/10 text-emerald-500' :
    score >= 60 ? 'bg-amber-500/10 text-amber-500' :
    'surface-inset text-[var(--color-surface-600)]';
  return (
    <span className={`badge ${color}`}>
      <Target className="w-3 h-3" />
      {score}%
    </span>
  );
}

/* ── Status pill ── */
function StatusPill({ status }) {
  const styles = {
    detected:   'bg-blue-500/10 text-blue-500',
    scanning:   'bg-cyan-500/10 text-cyan-500',
    generating: 'bg-violet-500/10 text-violet-500',
    ready:      'bg-emerald-500/10 text-emerald-500',
    published:  'badge-posted',
    dismissed:  'surface-inset text-[var(--color-surface-600)]',
    failed:     'bg-red-500/10 text-red-400',
  };
  const icons = {
    detected: Radar,
    scanning: RefreshCw,
    generating: Loader2,
    ready: Flame,
    published: CheckCircle,
    dismissed: X,
    failed: AlertTriangle,
  };
  const Icon = icons[status] || Clock;
  const cls = styles[status] || styles.detected;

  return (
    <span className={`badge ${cls}`}>
      <Icon className={`w-3 h-3 ${status === 'generating' ? 'animate-spin' : ''}`} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

/* ── Competition indicator ── */
function CompetitionDots({ level }) {
  const n = level === 'high' ? 3 : level === 'medium' ? 2 : 1;
  return (
    <span className="inline-flex items-center gap-0.5" title={`${level} competition`}>
      {[1, 2, 3].map(i => (
        <span
          key={i}
          className={`w-1.5 h-1.5 rounded-full transition-colors ${
            i <= n ? 'bg-[var(--color-brand-500)]' : 'bg-[var(--color-surface-300)]'
          }`}
        />
      ))}
      <span className="ml-1 text-xs text-[var(--color-surface-600)] capitalize">{level}</span>
    </span>
  );
}

/* ── Trend card ── */
function TrendCard({ alert, onPublish, onDismiss, onRegenerate }) {
  const [expanded, setExpanded] = useState(false);
  const isActionable = alert.status === 'detected' || alert.status === 'ready';
  const isGenerating = alert.status === 'generating';

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.25, ease }}
      className={`card bento-tile group overflow-hidden transition-all duration-200 ${
        alert.status === 'ready' ? 'ring-1 ring-emerald-500/20' : ''
      }`}
    >
      <div className="p-5 max-sm:p-4">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-[var(--color-surface-900)] leading-snug line-clamp-2">
              {alert.generated_title || alert.trend_topic}
            </h3>
            {alert.generated_title && alert.generated_title !== alert.trend_topic && (
              <p className="text-xs text-[var(--color-surface-600)] mt-0.5 truncate">
                Trend: {alert.trend_topic}
              </p>
            )}
          </div>
          <StatusPill status={alert.status} />
        </div>

        {/* Metrics row */}
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <ConfidenceBadge score={alert.confidence_score} />
          <span className="inline-flex items-center gap-1 text-xs text-[var(--color-surface-600)]">
            <TrendingUp className="w-3 h-3" />
            Demand: {alert.estimated_demand}/10
          </span>
          <CompetitionDots level={alert.competition_level} />
        </div>

        {/* Niche + source */}
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <span className="text-[11px] font-medium text-[var(--color-surface-700)] surface-inset px-2 py-0.5 rounded-[var(--radius-sm)]">
            {alert.niche}
          </span>
          <span className="text-[11px] text-[var(--color-surface-500)]">
            via {alert.trend_source.replace('_', ' ')}
          </span>
          {alert.auto_published && (
            <span className="inline-flex items-center gap-1 text-[11px] text-violet-500">
              <Bot className="w-3 h-3" />
              Auto
            </span>
          )}
        </div>

        {/* Reasoning (expandable) */}
        {alert.reasoning && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-[var(--color-surface-600)] hover:text-[var(--color-surface-800)] transition-colors mb-2"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? 'Hide reasoning' : 'Why this is trending'}
          </button>
        )}
        <AnimatePresence>
          {expanded && alert.reasoning && (
            <motion.p
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="text-xs text-[var(--color-surface-600)] leading-relaxed mb-3 overflow-hidden"
            >
              {alert.reasoning}
            </motion.p>
          )}
        </AnimatePresence>

        {/* Error message */}
        {alert.status === 'failed' && alert.error_message && (
          <p className="text-xs text-red-400 bg-red-500/5 rounded-[var(--radius-md)] px-3 py-2 mb-3">
            {alert.error_message}
          </p>
        )}

        {/* Action buttons */}
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          {(alert.status === 'detected') && (
            <button
              onClick={() => onPublish(alert.id)}
              className="btn-primary !px-3 !py-1.5 !text-xs !min-h-0 !rounded-[var(--radius-md)]"
            >
              <Play className="w-3 h-3" />
              Create Video
            </button>
          )}
          {alert.status === 'ready' && (
            <button
              onClick={() => onPublish(alert.id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold
                         bg-emerald-500 text-white rounded-[var(--radius-md)] hover:bg-emerald-600
                         transition-colors"
            >
              <Rocket className="w-3.5 h-3.5" />
              Publish Now
            </button>
          )}
          {alert.status === 'failed' && (
            <button
              onClick={() => onRegenerate(alert.id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold
                         bg-violet-500 text-white rounded-[var(--radius-md)] hover:bg-violet-600
                         transition-colors"
            >
              <RefreshCw className="w-3 h-3" />
              Retry
            </button>
          )}
          {isActionable && (
            <button
              onClick={() => onDismiss(alert.id)}
              className="btn-secondary !px-3 !py-1.5 !text-xs !min-h-0 !rounded-[var(--radius-md)]"
            >
              <X className="w-3 h-3" />
              Dismiss
            </button>
          )}
          {isGenerating && (
            <span className="inline-flex items-center gap-1.5 text-xs text-violet-500">
              <Loader2 className="w-3 h-3 animate-spin" />
              Creating video…
            </span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/* ── Stat card ── */
function StatCard({ label, value, icon: Icon, color = 'text-[var(--color-brand-500)]' }) {
  return (
    <div className="card bento-tile p-4 max-sm:p-3 flex items-center gap-3">
      <div className={`p-2 rounded-[var(--radius-md)] surface-inset ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-[var(--color-surface-900)]">{value}</p>
        <p className="text-xs text-[var(--color-surface-600)]">{label}</p>
      </div>
    </div>
  );
}

/* ── Settings panel ── */
function SettingsPanel({ settings, onSave, saving }) {
  const [local, setLocal] = useState(settings);

  useEffect(() => setLocal(settings), [settings]);

  const update = (key, val) => setLocal(prev => ({ ...prev, [key]: val }));

  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: 'auto', opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.25, ease }}
      className="overflow-hidden"
    >
      <div className="card bento-tile p-6 max-sm:p-4 mt-4">
        <h3 className="text-sm font-semibold text-[var(--color-surface-900)] mb-4 flex items-center gap-2">
          <SettingsIcon className="w-4 h-4 text-[var(--color-brand-500)]" />
          Trend Radar Settings
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Radar enabled */}
          <label className="flex items-center justify-between gap-3 p-3 rounded-[var(--radius-md)] surface-inset cursor-pointer">
            <div>
              <p className="text-xs font-medium text-[var(--color-surface-900)]">Radar Active</p>
              <p className="text-[11px] text-[var(--color-surface-600)]">Scan for trends automatically</p>
            </div>
            <input
              type="checkbox"
              checked={local.is_enabled}
              onChange={e => update('is_enabled', e.target.checked)}
              className="accent-[var(--color-brand-500)] w-4 h-4"
            />
          </label>

          {/* Autopilot */}
          <label className="flex items-center justify-between gap-3 p-3 rounded-[var(--radius-md)] surface-inset cursor-pointer">
            <div>
              <p className="text-xs font-medium text-[var(--color-surface-900)] flex items-center gap-1">
                <Bot className="w-3 h-3 text-violet-500" />
                Autopilot
              </p>
              <p className="text-[11px] text-[var(--color-surface-600)]">Auto-publish high-confidence trends</p>
            </div>
            <input
              type="checkbox"
              checked={local.autopilot_enabled}
              onChange={e => update('autopilot_enabled', e.target.checked)}
              className="accent-violet-500 w-4 h-4"
            />
          </label>

          {/* Min confidence for autopilot */}
          <div className="p-3 rounded-[var(--radius-md)] surface-inset">
            <p className="text-xs font-medium text-[var(--color-surface-900)] mb-2">
              Autopilot Min Confidence: {local.autopilot_min_confidence}%
            </p>
            <input
              type="range"
              min={40} max={100} step={5}
              value={local.autopilot_min_confidence}
              onChange={e => update('autopilot_min_confidence', +e.target.value)}
              className="w-full accent-[var(--color-brand-500)]"
            />
          </div>

          {/* Daily cap */}
          <div className="p-3 rounded-[var(--radius-md)] surface-inset">
            <p className="text-xs font-medium text-[var(--color-surface-900)] mb-2">
              Daily Auto-Publish Cap: {local.autopilot_daily_cap}
            </p>
            <input
              type="range"
              min={1} max={5} step={1}
              value={local.autopilot_daily_cap}
              onChange={e => update('autopilot_daily_cap', +e.target.value)}
              className="w-full accent-[var(--color-brand-500)]"
            />
          </div>

          {/* Min confidence threshold */}
          <div className="p-3 rounded-[var(--radius-md)] surface-inset">
            <p className="text-xs font-medium text-[var(--color-surface-900)] mb-2">
              Min Display Confidence: {local.min_confidence_threshold}%
            </p>
            <input
              type="range"
              min={20} max={90} step={5}
              value={local.min_confidence_threshold}
              onChange={e => update('min_confidence_threshold', +e.target.value)}
              className="w-full accent-[var(--color-brand-500)]"
            />
          </div>

          {/* Scan interval */}
          <div className="p-3 rounded-[var(--radius-md)] surface-inset">
            <p className="text-xs font-medium text-[var(--color-surface-900)] mb-1">
              Scan Interval
            </p>
            <select
              value={local.scan_interval_minutes}
              onChange={e => update('scan_interval_minutes', +e.target.value)}
              className="input-field !text-xs !py-1.5"
            >
              <option value={60}>Every hour</option>
              <option value={180}>Every 3 hours</option>
              <option value={360}>Every 6 hours</option>
              <option value={720}>Every 12 hours</option>
              <option value={1440}>Once daily</option>
            </select>
          </div>
        </div>

        <div className="mt-4 flex justify-end">
          <button
            onClick={() => onSave(local)}
            disabled={saving}
            className="btn-primary !text-xs !px-4 !py-2 !min-h-0"
          >
            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
            Save Settings
          </button>
        </div>
      </div>
    </motion.div>
  );
}


/* ══════════════════════════════════════════════════════════════════════
 * MAIN PAGE
 * ══════════════════════════════════════════════════════════════════════ */

export default function TrendRadar() {
  const toast = useToast();
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState(null);
  const [settings, setSettings] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState('active');
  const [error, setError] = useState('');
  const [needsNiches, setNeedsNiches] = useState(false);

  const filterMap = {
    active: 'detected,generating,ready',
    ready: 'ready',
    published: 'published',
    all: '',
  };

  const fetchAlerts = useCallback(async () => {
    try {
      const statusFilter = filterMap[filter] || '';
      const params = statusFilter ? { status_filter: statusFilter } : {};
      const { data } = await api.get('/api/trends', { params });
      setAlerts(data);
    } catch (err) {
      if (err.response?.status === 403) {
        setError('Trend Radar is not enabled for your account yet.');
      } else {
        console.error('Failed to fetch trends', err);
      }
    }
  }, [filter]);

  const fetchStats = useCallback(async () => {
    try {
      const { data } = await api.get('/api/trends/stats');
      setStats(data);
    } catch { /* silent */ }
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const { data } = await api.get('/api/trends/settings');
      setSettings(data);
    } catch { /* silent */ }
  }, []);

  const checkNiches = useCallback(async () => {
    try {
      const { data } = await api.get('/api/videos/channel-preferences');
      if (!data.niches || data.niches.length === 0) {
        setNeedsNiches(true);
        return false;
      }
      setNeedsNiches(false);
      return true;
    } catch {
      setNeedsNiches(true);
      return false;
    }
  }, []);

  // Initial load + poll every 30s
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const hasNiches = await checkNiches();
      if (hasNiches) {
        await Promise.all([fetchAlerts(), fetchStats(), fetchSettings()]);
      }
      setLoading(false);
    };
    load();
    const interval = setInterval(() => {
      if (!needsNiches) {
        fetchAlerts();
        fetchStats();
      }
    }, 30_000);
    return () => clearInterval(interval);
  }, [fetchAlerts, fetchStats, fetchSettings, checkNiches, needsNiches]);

  // Refetch when filter changes
  useEffect(() => { fetchAlerts(); }, [filter, fetchAlerts]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await api.post('/api/trends/scan');
      await Promise.all([fetchAlerts(), fetchStats()]);
      toast.success('Trend scan complete');
    } catch (err) {
      const detail = err.response?.data?.detail || 'Scan failed';
      if (detail.toLowerCase().includes('niche') || detail.toLowerCase().includes('onboarding')) {
        setNeedsNiches(true);
      } else {
        setError(detail);
        toast.error(detail);
      }
    } finally {
      setScanning(false);
    }
  };

  const handleNicheSetupComplete = async () => {
    setNeedsNiches(false);
    setLoading(true);
    await Promise.all([fetchAlerts(), fetchStats(), fetchSettings()]);
    setLoading(false);
    handleScan();
  };

  const handlePublish = async (id) => {
    try {
      await api.post(`/api/trends/${id}/publish`);
      toast.success('Trend video queued for creation');
      await Promise.all([fetchAlerts(), fetchStats()]);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Action failed';
      setError(msg);
      toast.error(msg);
    }
  };

  const handleDismiss = async (id) => {
    try {
      await api.post(`/api/trends/${id}/dismiss`);
      await Promise.all([fetchAlerts(), fetchStats()]);
    } catch (err) {
      setError(err.response?.data?.detail || 'Dismiss failed');
    }
  };

  const handleRegenerate = async (id) => {
    try {
      await api.post(`/api/trends/${id}/regenerate`);
      await Promise.all([fetchAlerts(), fetchStats()]);
    } catch (err) {
      setError(err.response?.data?.detail || 'Retry failed');
    }
  };

  const handleSaveSettings = async (data) => {
    setSaving(true);
    try {
      const { data: updated } = await api.put('/api/trends/settings', data);
      setSettings(updated);
      setShowSettings(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const readyCount = stats?.total_ready || 0;

  /* ── If no niches, show inline quick-setup ── */
  if (!loading && needsNiches) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-bold text-[var(--color-surface-900)] flex items-center gap-2">
            <Radar className="w-6 h-6 text-[var(--color-brand-500)]" />
            Trend Radar
          </h1>
          <p className="text-sm text-[var(--color-surface-600)] mt-0.5">
            Trend detection → video creation → one-tap publish
          </p>
        </div>

        <NicheSetup onComplete={handleNicheSetupComplete} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-[var(--color-surface-900)] flex items-center gap-2">
            <Radar className="w-6 h-6 text-[var(--color-brand-500)]" />
            Trend Radar
            {readyCount > 0 && (
              <span className="inline-flex items-center justify-center w-6 h-6 text-xs font-bold
                             bg-emerald-500 text-white rounded-full animate-pulse">
                {readyCount}
              </span>
            )}
          </h1>
          <p className="text-sm text-[var(--color-surface-600)] mt-0.5">
            Trend detection → video creation → one-tap publish
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="btn-secondary !text-xs !px-3 !py-2 !min-h-0"
          >
            <SettingsIcon className="w-3.5 h-3.5" />
            Settings
          </button>
          <button
            onClick={handleScan}
            disabled={scanning}
            className="btn-primary !text-xs !px-4 !py-2 !min-h-0"
          >
            {scanning ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Radar className="w-3.5 h-3.5" />
            )}
            {scanning ? 'Scanning…' : 'Scan Now'}
          </button>
        </div>
      </div>

      {/* ── Error banner ── */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="flex items-center justify-between gap-3 p-3 rounded-[var(--radius-md)]
                       bg-red-500/8 text-red-400 text-xs"
          >
            <span>{error}</span>
            <button onClick={() => setError('')} className="hover:text-red-300 transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Settings panel ── */}
      <AnimatePresence>
        {showSettings && settings && (
          <SettingsPanel settings={settings} onSave={handleSaveSettings} saving={saving} />
        )}
      </AnimatePresence>

      {/* ── Stats row ── */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Ready to Fire" value={stats.total_ready} icon={Flame} color="text-emerald-500" />
          <StatCard label="Creating" value={stats.total_generating} icon={Zap} color="text-violet-500" />
          <StatCard label="Detected" value={stats.total_detected} icon={Radar} color="text-blue-500" />
          <StatCard label="Published" value={stats.total_published} icon={Rocket} color="text-[var(--color-brand-500)]" />
        </div>
      )}

      {/* ── Filter tabs ── */}
      <div className="flex items-center gap-1 p-1 surface-s2 rounded-[var(--radius-lg)] w-fit">
        {[
          { key: 'active', label: 'Active', icon: Zap },
          { key: 'ready', label: 'Ready', icon: Flame },
          { key: 'published', label: 'Published', icon: CheckCircle },
          { key: 'all', label: 'All', icon: BarChart3 },
        ].map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)] transition-all duration-150 ${
              filter === key
                ? 'bg-[color-mix(in_srgb,var(--color-brand-500)_12%,transparent)] text-[var(--color-brand-500)]'
                : 'text-[var(--color-surface-600)] hover:text-[var(--color-surface-800)]'
            }`}
          >
            <Icon className="w-3 h-3" />
            {label}
          </button>
        ))}
      </div>

      {/* ── Alerts grid ── */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 text-[var(--color-brand-500)] animate-spin" />
        </div>
      ) : alerts.length === 0 ? (
        <div className="card bento-tile flex flex-col items-center justify-center py-16 text-center">
          <div className="p-4 rounded-2xl surface-inset mb-4">
            <Radar className="w-10 h-10 text-[var(--color-surface-500)]" />
          </div>
          <p className="text-sm font-medium text-[var(--color-surface-700)] mb-1">No trends found yet</p>
          <p className="text-xs text-[var(--color-surface-500)] max-w-xs">
            Hit "Scan Now" to detect trending topics in your niche, or wait for the
            automatic scan to kick in.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <AnimatePresence mode="popLayout">
            {alerts.map(alert => (
              <TrendCard
                key={alert.id}
                alert={alert}
                onPublish={handlePublish}
                onDismiss={handleDismiss}
                onRegenerate={handleRegenerate}
              />
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
