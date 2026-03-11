import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import {
  Layers,
  Plus,
  X,
  Send,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  Film,
  AlertTriangle,
  Trash2,
  ArrowLeft,
  Zap,
} from 'lucide-react';

const ease = [0.25, 0.1, 0.25, 1];

const STATUS_ICON = {
  queued: Clock,
  generating: Film,
  completed: CheckCircle,
  posted: CheckCircle,
  failed: XCircle,
};

const STATUS_COLOR = {
  queued: 'text-surface-500',
  generating: 'text-brand-400',
  completed: 'text-emerald-400',
  posted: 'text-emerald-400',
  failed: 'text-red-400',
};

const STATUS_LABEL = {
  queued: 'Queued',
  generating: 'Creating…',
  completed: 'Completed',
  posted: 'Posted',
  failed: 'Failed',
};

export default function BulkGenerator({ onBack, onDone, quota }) {
  const [topics, setTopics] = useState(['', '']);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Batch tracking state
  const [batchId, setBatchId] = useState(null);
  const [batchItems, setBatchItems] = useState([]);
  const [batchSummary, setBatchSummary] = useState(null);
  const pollRef = useRef(null);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function addTopic() {
    if (topics.length >= 20) return;
    setTopics((prev) => [...prev, '']);
  }

  function removeTopic(idx) {
    if (topics.length <= 2) return;
    setTopics((prev) => prev.filter((_, i) => i !== idx));
  }

  function updateTopic(idx, value) {
    setTopics((prev) => prev.map((t, i) => (i === idx ? value : t)));
  }

  const validTopics = topics.filter((t) => t.trim().length >= 3);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (validTopics.length < 2) {
      setError('Add at least 2 valid topics (3+ characters each).');
      return;
    }

    // Check for duplicates
    const lower = validTopics.map((t) => t.trim().toLowerCase());
    const dupes = lower.filter((t, i) => lower.indexOf(t) !== i);
    if (dupes.length > 0) {
      setError(`Duplicate topic: "${dupes[0]}"`);
      return;
    }

    setSubmitting(true);
    try {
      const { data } = await api.post('/api/videos/bulk-generate', {
        topics: validTopics.map((t) => t.trim()),
      });

      setBatchId(data.batch_id);
      // Start polling
      startPolling(data.batch_id);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 403) {
        setError(detail || 'Plan limit reached. Upgrade to bulk generate more videos.');
      } else if (err.response?.status === 429) {
        setError('Rate limit reached. Try again in a few minutes.');
      } else {
        setError(detail || 'Failed to start bulk generation. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  function startPolling(id) {
    async function poll() {
      try {
        const { data } = await api.get(`/api/videos/bulk-status/${id}`);
        setBatchItems(data.items || []);
        setBatchSummary({
          total: data.total,
          completed: data.completed,
          failed: data.failed,
          generating: data.generating,
          queued: data.queued,
        });

        // Stop polling if everything is done
        if (data.generating === 0 && data.queued === 0) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        // Keep polling — transient failure
      }
    }

    poll(); // Immediate first call
    pollRef.current = setInterval(poll, 4000);
  }

  const allDone = batchSummary && batchSummary.generating === 0 && batchSummary.queued === 0;

  // ── Batch Progress View ──
  if (batchId) {
    const total = batchSummary?.total || validTopics.length;
    const completed = batchSummary?.completed || 0;
    const failed = batchSummary?.failed || 0;
    const done = completed + failed;
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;

    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease }}
        className="card p-7 space-y-5"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-[10px] bg-brand-500/10 flex items-center justify-center">
              <Layers size={16} className="text-brand-400" />
            </div>
            <div>
              <h3 className="text-[15px] font-semibold text-white">
                Bulk Generation {allDone ? '— Complete' : '— In Progress'}
              </h3>
              <p className="text-[12px] text-surface-600">
                {completed} of {total} completed{failed > 0 ? `, ${failed} failed` : ''}
              </p>
            </div>
          </div>
          {allDone && (
            <motion.button
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => {
                if (onDone) onDone();
                onBack();
              }}
              className="btn-primary flex items-center gap-2 px-4 py-2 text-xs"
            >
              <CheckCircle size={13} />
              Done
            </motion.button>
          )}
        </div>

        {/* Overall Progress Bar */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] text-surface-600 font-medium">
              {allDone ? 'Batch complete' : `Processing video ${done + 1} of ${total}…`}
            </span>
            <span className="text-[10px] text-surface-500 tabular-nums">{pct}%</span>
          </div>
          <div className="h-[4px] rounded-full bg-surface-200 overflow-hidden">
            <motion.div
              className={`h-full rounded-full transition-colors ${
                allDone && failed === 0
                  ? 'bg-emerald-500'
                  : allDone && failed > 0
                    ? 'bg-amber-500'
                    : 'bg-brand-500'
              }`}
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
            />
          </div>
        </div>

        {/* Item List */}
        <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1">
          {batchItems.map((item, idx) => {
            const Icon = STATUS_ICON[item.status] || Clock;
            const color = STATUS_COLOR[item.status] || 'text-surface-500';
            const label = STATUS_LABEL[item.status] || item.status;

            return (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.03, duration: 0.15 }}
                className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg transition-colors ${
                  item.status === 'generating'
                    ? 'bg-brand-500/6 border border-brand-500/10'
                    : 'bg-surface-200/40'
                }`}
              >
                <span className="text-[11px] text-surface-500 font-mono w-5 text-center shrink-0">
                  {idx + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-white truncate">
                    {item.title || item.topic}
                  </p>
                  {item.status === 'generating' && item.progress_step && (
                    <div className="mt-1">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <RefreshCw size={9} className="text-brand-400 animate-spin" />
                        <span className="text-[10px] text-brand-400">{item.progress_step}</span>
                      </div>
                      <div className="h-[2px] rounded-full bg-surface-200 overflow-hidden w-full">
                        <motion.div
                          className="h-full rounded-full bg-brand-500"
                          animate={{ width: `${item.progress_pct || 0}%` }}
                          transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
                        />
                      </div>
                    </div>
                  )}
                  {item.status === 'failed' && item.error_message && (
                    <p className="text-[10px] text-red-400/80 mt-0.5 truncate">
                      {item.error_message}
                    </p>
                  )}
                </div>
                <div className={`flex items-center gap-1.5 shrink-0 ${color}`}>
                  <Icon size={13} className={item.status === 'generating' ? 'animate-pulse' : ''} />
                  <span className="text-[10px] font-medium">{label}</span>
                </div>
              </motion.div>
            );
          })}
        </div>
      </motion.div>
    );
  }

  // ── Topic Input Form ──
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease }}
      className="card p-7 space-y-5"
    >
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={onBack}
          className="w-8 h-8 rounded-lg bg-surface-200/60 hover:bg-surface-300/60 flex items-center justify-center transition-colors"
        >
          <ArrowLeft size={14} className="text-surface-600" />
        </button>
        <div className="w-10 h-10 rounded-[10px] bg-brand-500 flex items-center justify-center">
          <Layers size={16} className="text-white" />
        </div>
        <div>
          <h3 className="text-[15px] font-semibold text-white">Bulk Create Videos</h3>
          <p className="text-[12px] text-surface-600">
            Add 2–{quota?.plan === 'agency' ? '20' : quota?.plan === 'pro' ? '10' : '5'} topics and Tubevo will create them all sequentially
          </p>
        </div>
      </div>

      {/* Plan info */}
      {quota && (
        <div className="flex items-center gap-2 text-[11px] text-surface-500">
          <Zap size={11} className="text-brand-400" />
          <span>
            {quota.monthly_limit - quota.monthly_used >= 999_999
              ? 'Unlimited'
              : `${Math.max(0, quota.monthly_limit - quota.monthly_used)} video${quota.monthly_limit - quota.monthly_used !== 1 ? 's' : ''} remaining`}{' '}
            on your <span className="text-white capitalize">{quota.plan}</span> plan this month
          </span>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        {/* Topic List */}
        <div className="space-y-2">
          {topics.map((t, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.15 }}
              className="flex items-center gap-2"
            >
              <span className="text-[11px] text-surface-500 font-mono w-5 text-center shrink-0">
                {idx + 1}
              </span>
              <input
                type="text"
                value={t}
                onChange={(e) => updateTopic(idx, e.target.value)}
                placeholder={`Topic ${idx + 1}, e.g. "How to Build Wealth in Your 20s"`}
                className="input-premium flex-1"
                disabled={submitting}
              />
              {topics.length > 2 && (
                <button
                  type="button"
                  onClick={() => removeTopic(idx)}
                  disabled={submitting}
                  className="w-7 h-7 rounded-md bg-surface-200/60 hover:bg-red-500/10 flex items-center justify-center transition-colors group"
                >
                  <X size={12} className="text-surface-500 group-hover:text-red-400" />
                </button>
              )}
            </motion.div>
          ))}
        </div>

        {/* Add Topic Button */}
        <div className="mt-3">
          <button
            type="button"
            onClick={addTopic}
            disabled={submitting || topics.length >= 20}
            className="inline-flex items-center gap-1.5 text-[11px] text-surface-600 hover:text-brand-400 transition-colors disabled:opacity-40"
          >
            <Plus size={12} />
            Add another topic
          </button>
        </div>

        {/* Error */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-3 text-xs px-3 py-2.5 rounded-lg bg-red-500/6 text-red-400"
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Submit */}
        <div className="mt-5 flex items-center justify-between">
          <span className="text-[11px] text-surface-500">
            {validTopics.length} valid topic{validTopics.length !== 1 ? 's' : ''} ready
          </span>
          <motion.button
            type="submit"
            disabled={submitting || validTopics.length < 2}
            whileHover={!submitting ? { scale: 1.01 } : {}}
            whileTap={!submitting ? { scale: 0.99 } : {}}
            className="btn-primary flex items-center gap-2 px-5 py-2.5 text-sm"
          >
            {submitting ? (
              <>
                <RefreshCw size={14} className="animate-spin" />
                Queuing…
              </>
            ) : (
              <>
                <Send size={14} />
                Create {validTopics.length} Videos
              </>
            )}
          </motion.button>
        </div>
      </form>
    </motion.div>
  );
}
