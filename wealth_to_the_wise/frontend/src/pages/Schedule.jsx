import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonCard } from '../components/Skeleton';
import {
  Plus,
  CalendarClock,
  Trash2,
  Play,
  Pause,
  Sparkles,
  Clock,
  RotateCcw,
  ChevronDown,
  X,
  Zap,
  ListChecks,
} from 'lucide-react';

const ease = [0.25, 0.1, 0.25, 1];

const FREQUENCIES = [
  { value: 'daily', label: 'Daily' },
  { value: 'every_other_day', label: 'Every other day' },
  { value: 'twice_weekly', label: 'Twice a week' },
  { value: 'weekly', label: 'Weekly' },
];

const HOURS = Array.from({ length: 24 }, (_, i) => ({
  value: i,
  label: `${i === 0 ? '12' : i > 12 ? i - 12 : i}:00 ${i < 12 ? 'AM' : 'PM'} UTC`,
}));

export default function Schedule() {
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState('');

  async function fetchSchedules() {
    try {
      const { data } = await api.get('/api/schedules');
      setSchedules(data);
    } catch {
      // keep empty
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchSchedules();
  }, []);

  return (
    <FadeIn className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
            Automation
          </h1>
          <p className="text-sm text-surface-600 mt-2">
            Schedule recurring video generation — set topics, frequency, and let Tubevo handle the rest
          </p>
        </div>
        <motion.button
          onClick={() => setShowCreate(true)}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          className="btn-primary flex items-center gap-2 text-sm shrink-0"
        >
          <Plus size={16} />
          <span className="hidden sm:inline">New Schedule</span>
        </motion.button>
      </div>

      {/* Error */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-red-500/8 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-xl"
          >
            {error}
            <button onClick={() => setError('')} className="ml-2 underline">dismiss</button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Create modal */}
      <AnimatePresence>
        {showCreate && (
          <CreateScheduleModal
            onClose={() => setShowCreate(false)}
            onCreated={(s) => {
              setSchedules((prev) => [s, ...prev]);
              setShowCreate(false);
            }}
            setError={setError}
          />
        )}
      </AnimatePresence>

      {/* Content */}
      {loading ? (
        <div className="grid gap-4">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : schedules.length === 0 ? (
        <EmptyState onCreateClick={() => setShowCreate(true)} />
      ) : (
        <StaggerContainer className="space-y-4" staggerDelay={0.06}>
          {schedules.map((schedule) => (
            <StaggerItem key={schedule.id}>
              <ScheduleCard
                schedule={schedule}
                onUpdate={(updated) =>
                  setSchedules((prev) =>
                    prev.map((s) => (s.id === updated.id ? updated : s))
                  )
                }
                onDelete={(id) =>
                  setSchedules((prev) => prev.filter((s) => s.id !== id))
                }
                setError={setError}
              />
            </StaggerItem>
          ))}
        </StaggerContainer>
      )}
    </FadeIn>
  );
}


/* ═══════════════════════════════════════════════════════════════════ */
/*  Empty State                                                       */
/* ═══════════════════════════════════════════════════════════════════ */

function EmptyState({ onCreateClick }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.15, ease }}
      className="card-elevated p-12 text-center"
    >
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500/20 to-brand-600/10 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-brand-500/10">
        <CalendarClock size={28} className="text-brand-400" />
      </div>
      <h3 className="text-base font-semibold text-white mb-2">
        No schedules yet
      </h3>
      <p className="text-sm text-surface-600 max-w-sm mx-auto mb-6">
        Create your first automation schedule to generate and post videos on autopilot.
        Add topics, pick a frequency, and Tubevo will handle the rest.
      </p>
      <motion.button
        onClick={onCreateClick}
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
        className="btn-primary inline-flex items-center gap-2 text-sm"
      >
        <Plus size={16} />
        Create your first schedule
      </motion.button>
    </motion.div>
  );
}


/* ═══════════════════════════════════════════════════════════════════ */
/*  Create Schedule Modal                                              */
/* ═══════════════════════════════════════════════════════════════════ */

function CreateScheduleModal({ onClose, onCreated, setError }) {
  const [name, setName] = useState('');
  const [frequency, setFrequency] = useState('weekly');
  const [hour, setHour] = useState(14);
  const [topicInput, setTopicInput] = useState('');
  const [topics, setTopics] = useState([]);
  const [saving, setSaving] = useState(false);

  function addTopic() {
    const t = topicInput.trim();
    if (t && !topics.includes(t)) {
      setTopics((prev) => [...prev, t]);
      setTopicInput('');
    }
  }

  function removeTopic(idx) {
    setTopics((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleCreate() {
    if (!topics.length) {
      setError('Add at least one topic to create a schedule.');
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post('/api/schedules', {
        name: name.trim() || 'My Schedule',
        frequency,
        preferred_hour_utc: hour,
        topics,
        is_active: true,
      });
      onCreated(data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create schedule.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: 'spring', bounce: 0.15, duration: 0.5 }}
        className="card-elevated p-6 sm:p-8 w-full max-w-lg max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500/20 to-brand-600/10 flex items-center justify-center">
              <Sparkles size={20} className="text-brand-400" />
            </div>
            <h2 className="text-lg font-semibold text-white">New Schedule</h2>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg text-surface-600 hover:text-white hover:bg-surface-300/50 transition-all">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-5">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-surface-700 mb-2">Schedule Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Daily Finance Shorts"
              className="input-premium w-full"
            />
          </div>

          {/* Frequency */}
          <div>
            <label className="block text-sm font-medium text-surface-700 mb-2">Frequency</label>
            <div className="grid grid-cols-2 gap-2">
              {FREQUENCIES.map((f) => (
                <motion.button
                  key={f.value}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => setFrequency(f.value)}
                  className={`px-3 py-2.5 rounded-xl text-sm font-medium transition-all border ${
                    frequency === f.value
                      ? 'bg-brand-600/15 border-brand-500/40 text-brand-300'
                      : 'bg-surface-200/30 border-surface-300/30 text-surface-700 hover:border-surface-400/50'
                  }`}
                >
                  {f.label}
                </motion.button>
              ))}
            </div>
          </div>

          {/* Preferred Hour */}
          <div>
            <label className="block text-sm font-medium text-surface-700 mb-2">
              <Clock size={14} className="inline mr-1.5 -mt-0.5" />
              Preferred Time (UTC)
            </label>
            <select
              value={hour}
              onChange={(e) => setHour(Number(e.target.value))}
              className="input-premium w-full appearance-none cursor-pointer"
            >
              {HOURS.map((h) => (
                <option key={h.value} value={h.value}>{h.label}</option>
              ))}
            </select>
          </div>

          {/* Topics */}
          <div>
            <label className="block text-sm font-medium text-surface-700 mb-2">
              <ListChecks size={14} className="inline mr-1.5 -mt-0.5" />
              Topic Queue ({topics.length})
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={topicInput}
                onChange={(e) => setTopicInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTopic(); } }}
                placeholder="e.g. compound interest explained"
                className="input-premium flex-1"
              />
              <motion.button
                onClick={addTopic}
                whileTap={{ scale: 0.95 }}
                className="btn-secondary px-3 text-sm shrink-0"
              >
                Add
              </motion.button>
            </div>
            {topics.length > 0 && (
              <div className="mt-3 space-y-1.5 max-h-40 overflow-y-auto scrollbar-thin">
                {topics.map((t, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="flex items-center justify-between gap-2 bg-surface-200/40 border border-surface-300/30 rounded-lg px-3 py-2"
                  >
                    <span className="text-sm text-surface-800 truncate">
                      <span className="text-surface-500 text-xs mr-2">#{i + 1}</span>
                      {t}
                    </span>
                    <button
                      onClick={() => removeTopic(i)}
                      className="p-1 rounded-md text-surface-500 hover:text-red-400 hover:bg-red-500/10 transition-all shrink-0"
                    >
                      <X size={14} />
                    </button>
                  </motion.div>
                ))}
              </div>
            )}
            <p className="text-xs text-surface-500 mt-2">
              Topics are processed in order and cycle back to the beginning when all are used.
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 mt-8 pt-5 border-t border-surface-300/30">
          <motion.button
            onClick={onClose}
            whileTap={{ scale: 0.97 }}
            className="btn-secondary text-sm"
          >
            Cancel
          </motion.button>
          <motion.button
            onClick={handleCreate}
            disabled={saving || topics.length === 0}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            className="btn-primary text-sm flex items-center gap-2"
          >
            {saving ? (
              <RotateCcw size={14} className="animate-spin" />
            ) : (
              <Sparkles size={14} />
            )}
            {saving ? 'Creating…' : 'Create Schedule'}
          </motion.button>
        </div>
      </motion.div>
    </motion.div>
  );
}


/* ═══════════════════════════════════════════════════════════════════ */
/*  Schedule Card                                                      */
/* ═══════════════════════════════════════════════════════════════════ */

function ScheduleCard({ schedule, onUpdate, onDelete, setError }) {
  const [expanded, setExpanded] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const topics = schedule.topics || [];
  const currentTopic = topics[schedule.topic_index] || '—';
  const progress = topics.length > 0
    ? Math.round((schedule.topic_index / topics.length) * 100)
    : 0;

  async function toggleActive() {
    setToggling(true);
    try {
      const { data } = await api.patch(`/api/schedules/${schedule.id}`, {
        is_active: !schedule.is_active,
      });
      onUpdate(data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update schedule.');
    } finally {
      setToggling(false);
    }
  }

  async function triggerNow() {
    setTriggering(true);
    try {
      await api.post(`/api/schedules/${schedule.id}/run`);
      // Refresh the schedule to get updated topic_index
      const { data: updated } = await api.get('/api/schedules');
      const fresh = updated.find((s) => s.id === schedule.id);
      if (fresh) onUpdate(fresh);
      setError('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to trigger schedule.');
    } finally {
      setTriggering(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm('Delete this schedule? This cannot be undone.')) return;
    setDeleting(true);
    try {
      await api.delete(`/api/schedules/${schedule.id}`);
      onDelete(schedule.id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete schedule.');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <motion.div
      layout
      className={`card-elevated overflow-hidden transition-all ${
        schedule.is_active ? 'border-brand-500/20' : 'border-surface-300/30 opacity-70'
      }`}
    >
      {/* Top accent */}
      {schedule.is_active && (
        <div className="h-[2px] bg-gradient-to-r from-brand-500 to-accent-400 opacity-60" />
      )}

      {/* Header */}
      <div className="p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
              schedule.is_active
                ? 'bg-gradient-to-br from-brand-500/20 to-brand-600/10'
                : 'bg-surface-300/30'
            }`}>
              <CalendarClock size={18} className={schedule.is_active ? 'text-brand-400' : 'text-surface-500'} />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-semibold text-white truncate">{schedule.name}</h3>
              <p className="text-xs text-surface-600 mt-0.5">
                {schedule.frequency_label} · {topics.length} topic{topics.length !== 1 ? 's' : ''}
                {schedule.total_runs > 0 && ` · ${schedule.total_runs} run${schedule.total_runs !== 1 ? 's' : ''}`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {/* Toggle */}
            <motion.button
              onClick={toggleActive}
              disabled={toggling}
              whileTap={{ scale: 0.9 }}
              className={`relative w-11 h-6 rounded-full transition-all ${
                schedule.is_active
                  ? 'bg-gradient-to-r from-brand-500 to-brand-600 shadow-md shadow-brand-500/25'
                  : 'bg-surface-400'
              }`}
              title={schedule.is_active ? 'Pause schedule' : 'Activate schedule'}
            >
              <motion.span
                animate={{ x: schedule.is_active ? 20 : 0 }}
                transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                className="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-sm"
              />
            </motion.button>

            {/* Expand */}
            <motion.button
              onClick={() => setExpanded(!expanded)}
              whileTap={{ scale: 0.95 }}
              className="p-1.5 rounded-lg text-surface-600 hover:text-white hover:bg-surface-300/40 transition-all"
            >
              <motion.span animate={{ rotate: expanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
                <ChevronDown size={16} />
              </motion.span>
            </motion.button>
          </div>
        </div>

        {/* Status row */}
        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs">
          {/* Next topic */}
          <span className="flex items-center gap-1.5 bg-surface-200/40 border border-surface-300/30 rounded-lg px-2.5 py-1.5 text-surface-700">
            <Zap size={12} className="text-brand-400" />
            Next: <span className="text-white font-medium truncate max-w-[150px]">{currentTopic}</span>
          </span>

          {/* Next run */}
          {schedule.next_run_at && schedule.is_active && (
            <span className="flex items-center gap-1.5 bg-surface-200/40 border border-surface-300/30 rounded-lg px-2.5 py-1.5 text-surface-700">
              <Clock size={12} className="text-accent-400" />
              {new Date(schedule.next_run_at).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
              })}
            </span>
          )}

          {!schedule.is_active && (
            <span className="flex items-center gap-1.5 bg-surface-200/40 border border-surface-300/30 rounded-lg px-2.5 py-1.5 text-yellow-400">
              <Pause size={12} />
              Paused
            </span>
          )}
        </div>

        {/* Topic progress bar */}
        {topics.length > 1 && (
          <div className="mt-3">
            <div className="flex justify-between text-[10px] text-surface-500 mb-1">
              <span>Topic {schedule.topic_index + 1} of {topics.length}</span>
              <span>{progress}% through queue</span>
            </div>
            <div className="h-1 bg-surface-300/40 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-gradient-to-r from-brand-500 to-brand-400 rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${Math.max(progress, 3)}%` }}
                transition={{ duration: 0.6, ease }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Expanded section */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease }}
            className="overflow-hidden"
          >
            <div className="px-5 sm:px-6 pb-5 sm:pb-6 pt-0 space-y-4 border-t border-surface-300/20">
              {/* Topics list */}
              <div className="pt-4">
                <p className="text-xs font-medium text-surface-600 mb-2">Topic Queue</p>
                <div className="space-y-1.5 max-h-48 overflow-y-auto scrollbar-thin">
                  {topics.map((topic, i) => (
                    <div
                      key={i}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all ${
                        i === schedule.topic_index
                          ? 'bg-brand-600/10 border border-brand-500/20 text-brand-300'
                          : 'bg-surface-200/30 border border-surface-300/20 text-surface-700'
                      }`}
                    >
                      <span className={`text-[10px] font-bold w-5 ${
                        i === schedule.topic_index ? 'text-brand-400' : 'text-surface-500'
                      }`}>
                        {i + 1}
                      </span>
                      <span className="truncate">{topic}</span>
                      {i === schedule.topic_index && (
                        <span className="ml-auto text-[10px] uppercase tracking-wider font-bold text-brand-400 shrink-0">
                          Next
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div className="flex flex-wrap gap-2 pt-2">
                <motion.button
                  onClick={triggerNow}
                  disabled={triggering || topics.length === 0}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.97 }}
                  className="btn-primary text-xs flex items-center gap-1.5"
                >
                  {triggering ? (
                    <RotateCcw size={12} className="animate-spin" />
                  ) : (
                    <Play size={12} />
                  )}
                  {triggering ? 'Running…' : 'Run Now'}
                </motion.button>
                <motion.button
                  onClick={handleDelete}
                  disabled={deleting}
                  whileTap={{ scale: 0.97 }}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium text-red-400 hover:bg-red-500/10 border border-red-500/20 transition-all"
                >
                  <Trash2 size={12} />
                  {deleting ? 'Deleting…' : 'Delete'}
                </motion.button>
              </div>

              {/* Last run info */}
              {schedule.last_run_at && (
                <p className="text-[11px] text-surface-500">
                  Last run:{' '}
                  {new Date(schedule.last_run_at).toLocaleDateString('en-US', {
                    month: 'short', day: 'numeric', year: 'numeric',
                    hour: '2-digit', minute: '2-digit',
                  })}
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
