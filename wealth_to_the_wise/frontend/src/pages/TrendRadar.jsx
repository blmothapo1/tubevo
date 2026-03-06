import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Radar, Zap, Rocket, X, RefreshCw, Eye, Play, Bot,
  TrendingUp, AlertTriangle, CheckCircle, Clock, Flame,
  Settings as SettingsIcon, ChevronDown, ChevronUp,
  BarChart3, Target, Shield, Loader2
} from 'lucide-react';
import api from '../lib/api';

/* ── Confidence badge ── */
function ConfidenceBadge({ score }) {
  const color =
    score >= 80 ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' :
    score >= 60 ? 'text-amber-400 bg-amber-500/10 border-amber-500/20' :
    'text-zinc-400 bg-zinc-500/10 border-zinc-500/20';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-full border ${color}`}>
      <Target className="w-3 h-3" />
      {score}%
    </span>
  );
}

/* ── Status pill ── */
function StatusPill({ status }) {
  const styles = {
    detected: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
    scanning: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
    generating: 'text-violet-400 bg-violet-500/10 border-violet-500/20',
    ready: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    published: 'text-brand-400 bg-brand-500/10 border-brand-500/20',
    dismissed: 'text-zinc-500 bg-zinc-500/10 border-zinc-500/20',
    failed: 'text-red-400 bg-red-500/10 border-red-500/20',
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
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full border ${cls}`}>
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
          className={`w-1.5 h-1.5 rounded-full ${
            i <= n ? 'bg-brand-400' : 'bg-surface-700'
          }`}
        />
      ))}
      <span className="ml-1 text-xs text-muted capitalize">{level}</span>
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
      className={`bento-tile group relative overflow-hidden rounded-2xl border transition-all duration-200 ${
        alert.status === 'ready'
          ? 'border-emerald-500/30 bg-surface-800/80 shadow-lg shadow-emerald-500/5'
          : 'border-surface-700/50 bg-surface-800/60'
      }`}
    >
      {/* Hot indicator for ready items */}
      {alert.status === 'ready' && (
        <div className="absolute top-0 inset-x-0 h-[2px] bg-gradient-to-r from-transparent via-emerald-400 to-transparent" />
      )}

      <div className="p-5">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-primary leading-snug line-clamp-2">
              {alert.generated_title || alert.trend_topic}
            </h3>
            {alert.generated_title && alert.generated_title !== alert.trend_topic && (
              <p className="text-xs text-muted mt-0.5 truncate">
                Trend: {alert.trend_topic}
              </p>
            )}
          </div>
          <StatusPill status={alert.status} />
        </div>

        {/* Metrics row */}
        <div className="flex items-center gap-4 mb-3 text-xs">
          <ConfidenceBadge score={alert.confidence_score} />
          <span className="inline-flex items-center gap-1 text-muted">
            <TrendingUp className="w-3 h-3" />
            Demand: {alert.estimated_demand}/10
          </span>
          <CompetitionDots level={alert.competition_level} />
        </div>

        {/* Niche + source */}
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs text-muted bg-surface-700/50 px-2 py-0.5 rounded-md">
            {alert.niche}
          </span>
          <span className="text-xs text-muted/60">
            via {alert.trend_source.replace('_', ' ')}
          </span>
          {alert.auto_published && (
            <span className="inline-flex items-center gap-1 text-xs text-violet-400">
              <Bot className="w-3 h-3" />
              Auto
            </span>
          )}
        </div>

        {/* Reasoning (expandable) */}
        {alert.reasoning && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-muted hover:text-primary transition-colors mb-2"
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
              className="text-xs text-muted/80 leading-relaxed mb-3 overflow-hidden"
            >
              {alert.reasoning}
            </motion.p>
          )}
        </AnimatePresence>

        {/* Error message */}
        {alert.status === 'failed' && alert.error_message && (
          <p className="text-xs text-red-400/80 bg-red-500/5 rounded-lg px-3 py-2 mb-3">
            {alert.error_message}
          </p>
        )}

        {/* Action buttons */}
        <div className="flex items-center gap-2 mt-1">
          {(alert.status === 'detected') && (
            <button
              onClick={() => onPublish(alert.id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold
                         bg-brand-500 text-white rounded-lg hover:bg-brand-400
                         transition-colors shadow-sm"
            >
              <Play className="w-3 h-3" />
              Generate Video
            </button>
          )}
          {alert.status === 'ready' && (
            <button
              onClick={() => onPublish(alert.id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold
                         bg-emerald-500 text-white rounded-lg hover:bg-emerald-400
                         transition-colors shadow-sm"
            >
              <Rocket className="w-3.5 h-3.5" />
              Publish Now
            </button>
          )}
          {alert.status === 'failed' && (
            <button
              onClick={() => onRegenerate(alert.id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold
                         bg-violet-500 text-white rounded-lg hover:bg-violet-400
                         transition-colors shadow-sm"
            >
              <RefreshCw className="w-3 h-3" />
              Retry
            </button>
          )}
          {isActionable && (
            <button
              onClick={() => onDismiss(alert.id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium
                         text-muted hover:text-primary bg-surface-700/50 rounded-lg
                         hover:bg-surface-600/50 transition-colors"
            >
              <X className="w-3 h-3" />
              Dismiss
            </button>
          )}
          {isGenerating && (
            <span className="inline-flex items-center gap-1.5 text-xs text-violet-400">
              <Loader2 className="w-3 h-3 animate-spin" />
              Generating video…
            </span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/* ── Stat card ── */
function StatCard({ label, value, icon: Icon, color = 'text-brand-400' }) {
  return (
    <div className="bento-tile rounded-2xl border border-surface-700/50 bg-surface-800/60 p-4 flex items-center gap-3">
      <div className={`p-2 rounded-xl bg-surface-700/50 ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-primary">{value}</p>
        <p className="text-xs text-muted">{label}</p>
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
      className="overflow-hidden"
    >
      <div className="bento-tile rounded-2xl border border-surface-700/50 bg-surface-800/60 p-6 mt-4">
        <h3 className="text-sm font-semibold text-primary mb-4 flex items-center gap-2">
          <SettingsIcon className="w-4 h-4 text-brand-400" />
          Trend Radar Settings
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Radar enabled */}
          <label className="flex items-center justify-between gap-3 p-3 rounded-xl bg-surface-700/30">
            <div>
              <p className="text-xs font-medium text-primary">Radar Active</p>
              <p className="text-[11px] text-muted">Scan for trends automatically</p>
            </div>
            <input
              type="checkbox"
              checked={local.is_enabled}
              onChange={e => update('is_enabled', e.target.checked)}
              className="accent-brand-500 w-4 h-4"
            />
          </label>

          {/* Autopilot */}
          <label className="flex items-center justify-between gap-3 p-3 rounded-xl bg-surface-700/30">
            <div>
              <p className="text-xs font-medium text-primary flex items-center gap-1">
                <Bot className="w-3 h-3 text-violet-400" />
                Autopilot
              </p>
              <p className="text-[11px] text-muted">Auto-publish high-confidence trends</p>
            </div>
            <input
              type="checkbox"
              checked={local.autopilot_enabled}
              onChange={e => update('autopilot_enabled', e.target.checked)}
              className="accent-violet-500 w-4 h-4"
            />
          </label>

          {/* Min confidence for autopilot */}
          <div className="p-3 rounded-xl bg-surface-700/30">
            <p className="text-xs font-medium text-primary mb-2">
              Autopilot Min Confidence: {local.autopilot_min_confidence}%
            </p>
            <input
              type="range"
              min={40} max={100} step={5}
              value={local.autopilot_min_confidence}
              onChange={e => update('autopilot_min_confidence', +e.target.value)}
              className="w-full accent-brand-500"
            />
          </div>

          {/* Daily cap */}
          <div className="p-3 rounded-xl bg-surface-700/30">
            <p className="text-xs font-medium text-primary mb-2">
              Daily Auto-Publish Cap: {local.autopilot_daily_cap}
            </p>
            <input
              type="range"
              min={1} max={5} step={1}
              value={local.autopilot_daily_cap}
              onChange={e => update('autopilot_daily_cap', +e.target.value)}
              className="w-full accent-brand-500"
            />
          </div>

          {/* Min confidence threshold */}
          <div className="p-3 rounded-xl bg-surface-700/30">
            <p className="text-xs font-medium text-primary mb-2">
              Min Display Confidence: {local.min_confidence_threshold}%
            </p>
            <input
              type="range"
              min={20} max={90} step={5}
              value={local.min_confidence_threshold}
              onChange={e => update('min_confidence_threshold', +e.target.value)}
              className="w-full accent-brand-500"
            />
          </div>

          {/* Scan interval */}
          <div className="p-3 rounded-xl bg-surface-700/30">
            <p className="text-xs font-medium text-primary mb-1">
              Scan Interval
            </p>
            <select
              value={local.scan_interval_minutes}
              onChange={e => update('scan_interval_minutes', +e.target.value)}
              className="w-full bg-surface-800 text-primary text-xs rounded-lg px-2 py-1.5 border border-surface-600"
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
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold
                       bg-brand-500 text-white rounded-lg hover:bg-brand-400
                       transition-colors disabled:opacity-50"
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
  const [alerts, setAlerts] = useState([]);
  const [stats, setStats] = useState(null);
  const [settings, setSettings] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState('active');
  const [error, setError] = useState('');

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

  // Initial load + poll every 30s
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([fetchAlerts(), fetchStats(), fetchSettings()]);
      setLoading(false);
    };
    load();
    const interval = setInterval(() => {
      fetchAlerts();
      fetchStats();
    }, 30_000);
    return () => clearInterval(interval);
  }, [fetchAlerts, fetchStats, fetchSettings]);

  // Refetch when filter changes
  useEffect(() => { fetchAlerts(); }, [filter, fetchAlerts]);

  const handleScan = async () => {
    setScanning(true);
    try {
      const { data } = await api.post('/api/trends/scan');
      await Promise.all([fetchAlerts(), fetchStats()]);
    } catch (err) {
      setError(err.response?.data?.detail || 'Scan failed');
    } finally {
      setScanning(false);
    }
  };

  const handlePublish = async (id) => {
    try {
      await api.post(`/api/trends/${id}/publish`);
      await Promise.all([fetchAlerts(), fetchStats()]);
    } catch (err) {
      setError(err.response?.data?.detail || 'Action failed');
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
      setError(err.response?.data?.detail || 'Regeneration failed');
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

  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-primary flex items-center gap-2">
            <Radar className="w-6 h-6 text-brand-400" />
            Trend Radar
            {readyCount > 0 && (
              <span className="inline-flex items-center justify-center w-6 h-6 text-xs font-bold
                             bg-emerald-500 text-white rounded-full animate-pulse">
                {readyCount}
              </span>
            )}
          </h1>
          <p className="text-sm text-muted mt-0.5">
            Autonomous trend detection → video generation → one-tap publish
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium
                       text-muted hover:text-primary bg-surface-700/50 rounded-lg
                       hover:bg-surface-600/50 transition-colors"
          >
            <SettingsIcon className="w-3.5 h-3.5" />
            Settings
          </button>
          <button
            onClick={handleScan}
            disabled={scanning}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold
                       bg-brand-500 text-white rounded-lg hover:bg-brand-400
                       transition-colors disabled:opacity-50 shadow-sm"
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
            className="flex items-center justify-between gap-3 p-3 rounded-xl
                       bg-red-500/10 border border-red-500/20 text-red-400 text-xs"
          >
            <span>{error}</span>
            <button onClick={() => setError('')}>
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
          <StatCard label="Ready to Fire" value={stats.total_ready} icon={Flame} color="text-emerald-400" />
          <StatCard label="Generating" value={stats.total_generating} icon={Zap} color="text-violet-400" />
          <StatCard label="Detected" value={stats.total_detected} icon={Radar} color="text-blue-400" />
          <StatCard label="Published" value={stats.total_published} icon={Rocket} color="text-brand-400" />
        </div>
      )}

      {/* ── Filter tabs ── */}
      <div className="flex items-center gap-1 p-1 bg-surface-800/60 rounded-xl border border-surface-700/50 w-fit">
        {[
          { key: 'active', label: 'Active', icon: Zap },
          { key: 'ready', label: 'Ready', icon: Flame },
          { key: 'published', label: 'Published', icon: CheckCircle },
          { key: 'all', label: 'All', icon: BarChart3 },
        ].map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              filter === key
                ? 'bg-brand-500/15 text-brand-400'
                : 'text-muted hover:text-primary'
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
          <Loader2 className="w-6 h-6 text-brand-400 animate-spin" />
        </div>
      ) : alerts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Radar className="w-12 h-12 text-surface-600 mb-4" />
          <p className="text-sm font-medium text-muted mb-1">No trends found yet</p>
          <p className="text-xs text-muted/60 max-w-xs">
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
