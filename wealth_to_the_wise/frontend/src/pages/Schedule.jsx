import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonCard } from '../components/Skeleton';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
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
    <FadeIn className="max-w-4xl mx-auto space-y-7">
      {/* Header */}
      <PageHeader
        title="Automation"
        subtitle="Schedule recurring video generation"
        action={
          <motion.button
            onClick={() => setShowCreate(true)}
            whileTap={{ scale: 0.98 }}
            className="btn-primary flex items-center gap-2 text-xs uppercase tracking-wide shrink-0"
          >
            <Plus size={14} />
            <span className="hidden sm:inline">New Schedule</span>
          </motion.button>
        }
      />

      {/* Error */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-red-500/6 text-red-400 text-xs px-3 py-2.5 rounded-lg"
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
        <EmptyState
          icon={CalendarClock}
          title="No schedules yet"
          description="Create your first automation schedule to generate and post videos on autopilot."
          action={
            <motion.button
              onClick={() => setShowCreate(true)}
              whileTap={{ scale: 0.98 }}
              className="btn-primary inline-flex items-center gap-2 text-xs uppercase tracking-wide"
            >
              <Plus size={16} />
              Create your first schedule
            </motion.button>
          }
        />
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
        initial={{ opacity: 0, scale: 0.97, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 12 }}
        transition={{ type: 'tween', duration: 0.2 }}
        className="card p-7 w-full max-w-lg max-h-[85vh] overflow-y-auto !rounded-[20px]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-[10px] bg-brand-500/10 flex items-center justify-center">
              <Sparkles size={16} className="text-brand-400" />
            </div>
            <h2 className="text-[15px] font-semibold text-white">New Schedule</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded text-surface-600 hover:text-white hover:bg-surface-300/50 transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="space-y-6">
          {/* Name */}
          <div>
            <label className="block text-[10px] font-semibold text-surface-500 mb-2 uppercase tracking-wider">Schedule Name</label>
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
            <label className="block text-[10px] font-semibold text-surface-500 mb-2 uppercase tracking-wider">Frequency</label>
            <div className="grid grid-cols-2 gap-2.5">
              {FREQUENCIES.map((f) => (
                <motion.button
                  key={f.value}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => setFrequency(f.value)}
                  className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                    frequency === f.value
                      ? 'bg-brand-600/15 text-brand-300'
                      : 'bg-surface-200/30 text-surface-700 hover:bg-surface-300/40'
                  }`}
                >
                  {f.label}
                </motion.button>
              ))}
            </div>
          </div>

          {/* Preferred Hour */}
          <div>
            <label className="block text-[10px] font-semibold text-surface-500 mb-2 uppercase tracking-wider">
              <Clock size={12} className="inline mr-1 -mt-0.5" />
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
            <label className="block text-[10px] font-semibold text-surface-500 mb-2 uppercase tracking-wider">
              <ListChecks size={12} className="inline mr-1 -mt-0.5" />
              Topic Queue ({topics.length})
            </label>
            <div className="flex gap-2.5">
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
              <div className="mt-3 space-y-2 max-h-40 overflow-y-auto scrollbar-thin">
                {topics.map((t, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="flex items-center justify-between gap-2 bg-surface-200/40 rounded-lg px-3 py-1.5"
                  >
                    <span className="text-xs text-surface-800 truncate">
                      <span className="text-surface-500 text-[10px] mr-2 tabular-nums">#{i + 1}</span>
                      {t}
                    </span>
                    <button
                      onClick={() => removeTopic(i)}
                      className="p-1 rounded text-surface-500 hover:text-red-400 hover:bg-red-500/10 transition-colors shrink-0"
                    >
                      <X size={14} />
                    </button>
                  </motion.div>
                ))}
              </div>
            )}
            <p className="text-[11px] text-surface-500 mt-1.5">
              Topics are processed in order and cycle back to the beginning when all are used.
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3 mt-7 pt-5">
          <motion.button
            onClick={onClose}
            whileTap={{ scale: 0.98 }}
            className="btn-secondary text-xs"
          >
            Cancel
          </motion.button>
          <motion.button
            onClick={handleCreate}
            disabled={saving || topics.length === 0}
            whileTap={{ scale: 0.98 }}
            className="btn-primary text-xs flex items-center gap-1.5"
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
      className={`card overflow-hidden transition-all ${
        !schedule.is_active ? 'opacity-70' : ''
      }`}
    >
      {/* Top accent */}
      {schedule.is_active && (
        <div className="h-[1px] bg-brand-500 opacity-40" />
      )}

      {/* Header */}
      <div className="p-5 sm:p-7">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-4 min-w-0">
            <div className={`w-10 h-10 rounded-[10px] flex items-center justify-center shrink-0 ${
              schedule.is_active
                ? 'bg-brand-500/10'
                : 'bg-surface-300/30'
            }`}>
              <CalendarClock size={16} className={schedule.is_active ? 'text-brand-400' : 'text-surface-500'} />
            </div>
            <div className="min-w-0">
              <h3 className="text-[15px] font-semibold text-white truncate">{schedule.name}</h3>
              <p className="text-[12px] text-surface-600 mt-1">
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
              className={`relative w-[44px] h-[24px] rounded-full transition-colors duration-150 ${
                schedule.is_active
                  ? 'bg-brand-500'
                  : 'bg-surface-400'
              }`}
              title={schedule.is_active ? 'Pause schedule' : 'Activate schedule'}
            >
              <motion.span
                animate={{ x: schedule.is_active ? 20 : 0 }}
                transition={{ type: 'tween', duration: 0.15 }}
                className="absolute top-[2px] left-[2px] w-5 h-5 bg-white rounded-full shadow-sm"
              />
            </motion.button>

            {/* Expand */}
            <motion.button
              onClick={() => setExpanded(!expanded)}
              whileTap={{ scale: 0.95 }}
              className="p-1.5 rounded text-surface-600 hover:text-white hover:bg-surface-300/40 transition-colors"
            >
              <motion.span animate={{ rotate: expanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
                <ChevronDown size={16} />
              </motion.span>
            </motion.button>
          </div>
        </div>

        {/* Status row */}
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
          {/* Next topic */}
          <span className="flex items-center gap-1.5 bg-surface-200/40 rounded-lg px-2 py-1 text-surface-700">
            <Zap size={11} className="text-brand-400" />
            Next: <span className="text-white font-medium truncate max-w-[140px]">{currentTopic}</span>
          </span>

          {/* Next run */}
          {schedule.next_run_at && schedule.is_active && (
            <span className="flex items-center gap-1.5 bg-surface-200/40 rounded-lg px-2 py-1 text-surface-700">
              <Clock size={11} className="text-accent-400" />
              {new Date(schedule.next_run_at).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
              })}
            </span>
          )}

          {!schedule.is_active && (
            <span className="flex items-center gap-1.5 bg-surface-200/40 rounded-lg px-2 py-1 text-yellow-400">
              <Pause size={11} />
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
            <div className="h-[3px] bg-surface-300/40 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-brand-500 rounded-full"
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
            <div className="px-5 sm:px-7 pb-5 sm:pb-7 pt-0 space-y-4">
              {/* Topics list */}
              <div className="pt-3">
                <p className="text-[10px] font-semibold text-surface-500 uppercase tracking-widest mb-2">Topic Queue</p>
                <div className="space-y-1 max-h-48 overflow-y-auto scrollbar-thin">
                  {topics.map((topic, i) => (
                    <div
                      key={i}
                      className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs transition-colors ${
                        i === schedule.topic_index
                          ? 'bg-brand-600/10 text-brand-300'
                          : 'bg-surface-200/30 text-surface-700'
                      }`}
                    >
                      <span className={`text-[10px] font-bold w-4 tabular-nums ${
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
              <div className="flex flex-wrap gap-2 pt-1.5">
                <motion.button
                  onClick={triggerNow}
                  disabled={triggering || topics.length === 0}
                  whileTap={{ scale: 0.98 }}
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
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium text-red-400 hover:bg-red-500/10 transition-colors"
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
