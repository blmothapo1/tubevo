import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonVideoList } from '../components/Skeleton';
import ConfettiCelebration from '../components/ConfettiCelebration';
import EmptyState from '../components/EmptyState';
import ScriptRefiner from '../components/ScriptRefiner';
import {
  CheckCircle,
  XCircle,
  Clock,
  Upload,
  AlertTriangle,
  Film,
  Sparkles,
  Send,
  ExternalLink,
  RefreshCw,
  Wand2,
  Video,
  Download,
  RotateCcw,
  Layers,
  Lightbulb,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  Trash2,
  FileText,
} from 'lucide-react';

const ease = [0.25, 0.1, 0.25, 1];

const statusConfig = {
  pending:    { label: 'Pending',      badge: 'badge-pending',     icon: Clock },
  generating: { label: 'Creating…',   badge: 'badge-generating',  icon: Film },
  completed:  { label: 'Completed',    badge: 'badge-completed',   icon: CheckCircle },
  posted:     { label: 'Posted',       badge: 'badge-posted',      icon: Upload },
  failed:     { label: 'Failed',       badge: 'badge-failed',      icon: AlertTriangle },
};

// ── Pipeline step labels for ETA estimation ──
// When using the two-phase flow (generate-script → refine → render),
// the render phase skips script/metadata since those are already done.
const PIPELINE_STEPS = [
  { label: 'Writing script', pctStart: 0, pctEnd: 15 },
  { label: 'Crafting metadata', pctStart: 15, pctEnd: 22 },
  { label: 'Producing voiceover', pctStart: 22, pctEnd: 38 },
  { label: 'Planning scenes', pctStart: 38, pctEnd: 45 },
  { label: 'Downloading footage', pctStart: 45, pctEnd: 60 },
  { label: 'Building video', pctStart: 60, pctEnd: 78 },
  { label: 'Designing thumbnail', pctStart: 78, pctEnd: 85 },
  { label: 'Uploading to YouTube', pctStart: 85, pctEnd: 100 },
];

function estimateTimeRemaining(pct, startedAt) {
  if (!startedAt || pct <= 0) return null;
  const elapsed = (Date.now() / 1000) - startedAt;
  if (elapsed < 3) return null; // too early to estimate
  const totalEstimate = elapsed / (pct / 100);
  const remaining = Math.max(0, totalEstimate - elapsed);
  if (remaining < 60) return `~${Math.ceil(remaining)}s remaining`;
  return `~${Math.ceil(remaining / 60)}m remaining`;
}

// ── Live Progress Bar component ──
function RenderProgressBar({ pct, step, startedAt }) {
  const clampedPct = Math.min(100, Math.max(0, pct || 0));
  const eta = estimateTimeRemaining(clampedPct, startedAt);

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2, ease }}
      className="mt-3"
    >
      {/* Step label + ETA */}
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] text-brand-400 font-medium flex items-center gap-1.5">
          <RefreshCw size={10} className="animate-spin" />
          {step || 'Starting…'}
        </span>
        {eta && (
          <span className="text-[10px] text-surface-600 tabular-nums">{eta}</span>
        )}
      </div>

      {/* Progress bar track */}
      <div className="h-[3px] rounded-full bg-surface-200 overflow-hidden">
        <motion.div
          className="h-full rounded-full bg-brand-500"
          initial={{ width: 0 }}
          animate={{ width: `${clampedPct}%` }}
          transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
        />
      </div>

      {/* Percentage */}
      <div className="flex justify-end mt-0.5">
        <span className="text-[10px] text-surface-600 tabular-nums">{clampedPct}%</span>
      </div>
    </motion.div>
  );
}

export default function Videos() {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [topic, setTopic] = useState('');
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [activeJobId, setActiveJobId] = useState(null);
  const pollRef = useRef(null);

  // ── Phase 6: Progress tracking state ──
  const [progressPct, setProgressPct] = useState(0);
  const [progressStep, setProgressStep] = useState('');
  const [pipelineStartedAt, setPipelineStartedAt] = useState(null);

  // ── Phase 6: Queue indicator state ──
  const [queueInfo, setQueueInfo] = useState(null);

  // ── Phase 6: Regenerating state (track which video is being regenerated) ──
  const [regeneratingId, setRegeneratingId] = useState(null);

  // ── Clear failed videos state ──
  const [clearingFailed, setClearingFailed] = useState(false);
  const failedCount = videos.filter((v) => v.status === 'failed').length;

  // ── Topic suggestions state ──
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // ── Script Refinement: two-phase creation state ──
  // Phase: 'topic' (default) → 'refine' → 'render'
  const [creationPhase, setCreationPhase] = useState('topic');
  const [scriptData, setScriptData] = useState(null); // { script, metadata, readTime, topic, videoId }
  const [scriptLoading, setScriptLoading] = useState(false);

  async function fetchSuggestions() {
    setSuggestionsLoading(true);
    try {
      const { data } = await api.get('/api/videos/topic-suggestions');
      setSuggestions(data.suggestions || []);
      setShowSuggestions(true);
    } catch {
      // silent — button just shows error state briefly
    } finally {
      setSuggestionsLoading(false);
    }
  }

  // Confetti for first successful video
  const [showConfetti, setShowConfetti] = useState(false);
  const hasSeenConfetti = useRef(
    (() => { try { return localStorage.getItem('hasSeenFirstVideoConfetti') === 'true'; } catch { return false; } })()
  );

  const triggerFirstVideoConfetti = useCallback(() => {
    if (hasSeenConfetti.current) return;
    hasSeenConfetti.current = true;
    try { localStorage.setItem('hasSeenFirstVideoConfetti', 'true'); } catch { /* silent */ }
    setShowConfetti(true);
  }, []);

  const fetchVideos = useCallback(async () => {
    try {
      const { data } = await api.get('/api/videos/history');
      setVideos(data);
    } catch {
      // keep empty
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVideos();
  }, [fetchVideos]);

  // ── Phase 6: Fetch render queue info periodically ──
  useEffect(() => {
    let cancelled = false;
    async function fetchQueue() {
      try {
        const { data } = await api.get('/api/videos/queue');
        if (!cancelled) setQueueInfo(data);
      } catch { /* silent */ }
    }
    fetchQueue();
    const queueInterval = setInterval(fetchQueue, 15000);
    return () => { cancelled = true; clearInterval(queueInterval); };
  }, []);

  // ── Poll for status when a job is active ──
  const pollFailCountRef = useRef(0);
  useEffect(() => {
    if (!activeJobId) return;
    pollFailCountRef.current = 0;

    async function pollStatus() {
      try {
        const { data } = await api.get(`/api/videos/${activeJobId}/status`);
        pollFailCountRef.current = 0; // reset on success

        // Update progress in real-time
        setProgressPct(data.progress_pct || 0);
        setProgressStep(data.progress_step || '');
        if (data.started_at && !pipelineStartedAt) {
          setPipelineStartedAt(data.started_at);
        }

        if (data.status === 'generating') return;

        clearInterval(pollRef.current);
        pollRef.current = null;
        setActiveJobId(null);
        setGenerating(false);
        setProgressPct(0);
        setProgressStep('');
        setPipelineStartedAt(null);

        if (data.status === 'failed') {
          setMessage({ type: 'error', text: data.error_message || 'Video creation failed.' });
        } else if (data.status === 'posted') {
          setMessage({ type: 'success', text: `Video "${data.title}" created and posted to YouTube!` });
          triggerFirstVideoConfetti();
        } else {
          setMessage({ type: 'success', text: `Video "${data.title}" created successfully!` });
          triggerFirstVideoConfetti();
        }
        fetchVideos();
      } catch (err) {
        pollFailCountRef.current += 1;
        // Stop polling after 10 consecutive failures (e.g. 401 auth expired)
        if (pollFailCountRef.current >= 10) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setActiveJobId(null);
          setGenerating(false);
          setProgressPct(0);
          setProgressStep('');
          setPipelineStartedAt(null);
          setMessage({ type: 'error', text: 'Lost connection to the server. Please refresh the page.' });
        }
      }
    }

    pollRef.current = setInterval(pollStatus, 3000); // Poll every 3s for snappier progress
    pollStatus();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeJobId, fetchVideos, triggerFirstVideoConfetti, pipelineStartedAt]);

  // ── Phase 6: Duplicate submission guard ──
  const isTopicAlreadyGenerating = useCallback((topicText) => {
    return videos.some(
      (v) => v.status === 'generating' && v.topic.toLowerCase().trim() === topicText.toLowerCase().trim()
    );
  }, [videos]);

  async function handleGenerate(e) {
    e.preventDefault();
    if (!topic.trim() || topic.trim().length < 3) {
      setMessage({ type: 'error', text: 'Topic must be at least 3 characters.' });
      return;
    }

    // Phase 6: Block duplicate topic submission
    if (isTopicAlreadyGenerating(topic.trim())) {
      setMessage({ type: 'error', text: 'This topic is already being created. Please wait for it to finish.' });
      return;
    }

    // ── Phase 1: Generate script only (fast ~15s) ───────────────────
    setScriptLoading(true);
    setMessage({ type: '', text: '' });

    try {
      const { data } = await api.post('/api/videos/generate-script', { topic: topic.trim() });

      // Transition to the Script Refiner
      setScriptData({
        script: data.script,
        metadata: data.metadata,
        readTime: data.read_time,
        topic: data.topic,
        videoId: data.video_id,
      });
      setCreationPhase('refine');
      setTopic('');
      setMessage({ type: '', text: '' });
      fetchVideos(); // Refresh list to show the new pending record

    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 429) {
        setMessage({ type: 'error', text: 'Rate limit reached. Try again later.' });
      } else if (err.response?.status === 403) {
        setMessage({ type: 'error', text: detail || 'You have reached your plan limit this month.' });
      } else {
        setMessage({ type: 'error', text: detail || 'Script generation failed. Please try again.' });
      }
    } finally {
      setScriptLoading(false);
    }
  }

  // ── Script Refiner: handle "Produce Video" ────────────────────────
  async function handleProduceVideo({ videoId, script, topic: videoTopic, voiceStyle, metadata }) {
    setCreationPhase('topic'); // Go back to the main view
    setScriptData(null);
    setGenerating(true);
    setMessage({ type: '', text: '' });
    setProgressPct(0);
    setProgressStep('Starting render…');

    try {
      const { data } = await api.post('/api/videos/render', {
        video_id: videoId,
        script,
        topic: videoTopic,
        voice_style: voiceStyle,
        metadata,
      });

      if (data.status === 'generating' && data.video_id) {
        setActiveJobId(data.video_id);
        setPipelineStartedAt(Date.now() / 1000);
        setMessage({ type: 'info', text: data.message });
        fetchVideos();
      } else if (data.status === 'failed') {
        setMessage({ type: 'error', text: data.message });
        setGenerating(false);
        setProgressStep('');
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409) {
        setMessage({ type: 'error', text: detail || 'A video is already in production. Please wait for it to finish.' });
      } else {
        setMessage({ type: 'error', text: detail || 'Video render failed.' });
      }
      setGenerating(false);
      setProgressStep('');
    }
  }

  // ── Clear all failed videos ──
  async function handleClearFailed() {
    setClearingFailed(true);
    try {
      const { data } = await api.delete('/api/videos/clear-failed');
      setMessage({ type: 'success', text: `Cleared ${data.deleted} failed video${data.deleted === 1 ? '' : 's'}.` });
      fetchVideos();
    } catch {
      setMessage({ type: 'error', text: 'Failed to clear failed videos.' });
    } finally {
      setClearingFailed(false);
    }
  }

  // ── Phase 6: Regenerate handler ──
  async function handleRegenerate(videoId) {
    setRegeneratingId(videoId);
    setMessage({ type: '', text: '' });
    try {
      const { data } = await api.post(`/api/videos/${videoId}/regenerate`);
      if (data.status === 'generating' && data.video_id) {
        setActiveJobId(data.video_id);
        setGenerating(true);
        setPipelineStartedAt(Date.now() / 1000);
        setProgressPct(0);
        setProgressStep('Starting…');
        setMessage({ type: 'info', text: data.message });
        fetchVideos();
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409) {
        setMessage({ type: 'error', text: detail || 'A video is already in production. Please wait for it to finish.' });
      } else {
        setMessage({ type: 'error', text: detail || 'Retry failed.' });
      }
    } finally {
      setRegeneratingId(null);
    }
  }

  // ── Phase 6: Download handler ──
  async function handleDownload(videoId, title) {
    try {
      const response = await api.get(`/api/videos/${videoId}/download`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(title || 'video').replace(/\s+/g, '_').slice(0, 60)}.mp4`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      setMessage({ type: 'error', text: 'Download failed. The file may not be available on this server.' });
    }
  }

  return (
    <FadeIn className="max-w-5xl mx-auto space-y-6 sm:space-y-7">
      {/* Confetti on first successful video — additive */}
      <ConfettiCelebration show={showConfetti} onDone={() => setShowConfetti(false)} />

      {/* Header + Queue Indicator */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[20px] sm:text-[24px] font-semibold text-white tracking-tight">Videos</h1>
          <p className="text-[12px] text-surface-600 mt-2 uppercase tracking-[0.08em] font-medium">
            Create & manage your videos
          </p>
        </div>

        {/* Phase 6: Render Queue Indicator */}
        <AnimatePresence>
          {queueInfo && queueInfo.global_generating > 0 && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-[6px] bg-brand-500/6 shrink-0"
            >
              <Layers size={12} className="text-brand-400" />
              <span className="text-[10px] text-brand-400 font-semibold uppercase tracking-wider">
                {queueInfo.global_generating} rendering
              </span>
              <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-soft-pulse" />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Script Loading Overlay ── */}
      <AnimatePresence>
        {scriptLoading && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.3, ease }}
            className="card p-10 flex flex-col items-center justify-center text-center space-y-4"
          >
            <div className="w-12 h-12 rounded-full bg-brand-500/10 flex items-center justify-center">
              <FileText size={20} className="text-brand-400 animate-pulse" />
            </div>
            <div>
              <h3 className="text-[15px] font-semibold text-white">Crafting your script…</h3>
              <p className="text-[12px] text-surface-600 mt-1">
                Generating script, metadata & thumbnails — about 15 seconds
              </p>
            </div>
            <div className="w-32 h-[3px] rounded-full bg-surface-200 overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-brand-500"
                initial={{ width: '0%' }}
                animate={{ width: '90%' }}
                transition={{ duration: 14, ease: 'linear' }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Phase: Script Refiner ── */}
      {creationPhase === 'refine' && scriptData && !scriptLoading && (
        <ScriptRefiner
          script={scriptData.script}
          metadata={scriptData.metadata}
          readTime={scriptData.readTime}
          topic={scriptData.topic}
          videoId={scriptData.videoId}
          onBack={() => {
            setCreationPhase('topic');
            setScriptData(null);
          }}
          onProduce={handleProduceVideo}
        />
      )}

      {/* ── Phase: Topic Input + Video List (default) ── */}
      {creationPhase === 'topic' && !scriptLoading && (
      <>
      {/* Generate Form */}
      <motion.form
        onSubmit={handleGenerate}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.1, ease }}
        className="card p-7"
      >
        <div className="flex items-center gap-4 mb-5">
          <div className="w-10 h-10 rounded-[10px] bg-brand-500 flex items-center justify-center">
            <Wand2 size={16} className="text-white" />
          </div>
          <div>
            <h3 className="text-[15px] font-semibold text-white">Create a New Video</h3>
            <p className="text-[12px] text-surface-600">Enter a topic and Tubevo handles the rest</p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Enter a topic, e.g. 'Why Budgeting Fails'"
            className="input-premium flex-1"
            disabled={generating}
            data-tour="topic-input"
          />
          <motion.button
            type="submit"
            disabled={generating}
            whileHover={!generating ? { scale: 1.01 } : {}}
            whileTap={!generating ? { scale: 0.99 } : {}}
            data-tour="generate-button"
            className="btn-primary flex items-center justify-center gap-2 px-5 py-2.5 whitespace-nowrap"
          >
            {generating ? (
              <>
                <RefreshCw size={14} className="animate-spin" />
                Creating…
              </>
            ) : (
              <>
                <Send size={14} />
                Create
              </>
            )}
          </motion.button>
        </div>

        {/* Topic Suggestions — collapsible panel */}
        {!generating && (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => showSuggestions ? setShowSuggestions(false) : fetchSuggestions()}
              disabled={suggestionsLoading}
              className="inline-flex items-center gap-1.5 text-[11px] text-surface-600 hover:text-brand-400 transition-colors"
            >
              {suggestionsLoading ? (
                <RefreshCw size={11} className="animate-spin" />
              ) : (
                <Lightbulb size={11} />
              )}
              {suggestionsLoading ? 'Finding topics…' : showSuggestions ? 'Hide suggestions' : 'Suggest topics for me'}
              {showSuggestions ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            </button>

            <AnimatePresence>
              {showSuggestions && suggestions.length > 0 && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.2, ease }}
                  className="mt-2 space-y-1.5"
                >
                  {suggestions.map((s, i) => (
                    <motion.button
                      type="button"
                      key={i}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05, duration: 0.15 }}
                      onClick={() => { setTopic(s.topic); setShowSuggestions(false); }}
                      className="w-full text-left px-3 py-2 rounded-lg bg-surface-200/60 hover:bg-surface-300/60 transition-all group"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs text-white font-medium group-hover:text-brand-400 transition-colors truncate">{s.topic}</span>
                        <span className="flex items-center gap-1 text-[10px] text-surface-500 whitespace-nowrap">
                          <TrendingUp size={10} className={s.score >= 7 ? 'text-emerald-400' : s.score >= 4 ? 'text-amber-400' : 'text-surface-500'} />
                          {s.score}/10
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] text-surface-500 px-1.5 py-0.5 rounded bg-surface-300/40">{s.angle}</span>
                        <span className="text-[10px] text-surface-600 truncate">{s.why}</span>
                      </div>
                    </motion.button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Phase 6: Live Progress Bar — shown during generation */}
        <AnimatePresence>
          {generating && activeJobId && (
            <RenderProgressBar
              pct={progressPct}
              step={progressStep}
              startedAt={pipelineStartedAt}
            />
          )}
        </AnimatePresence>

        {/* Message Banner */}
        <AnimatePresence mode="wait">
          {message.text && (
            <motion.div
              key={message.text}
              initial={{ opacity: 0, y: -6, height: 0 }}
              animate={{ opacity: 1, y: 0, height: 'auto' }}
              exit={{ opacity: 0, y: -6, height: 0 }}
              transition={{ duration: 0.2, ease }}
              className={`mt-3 text-xs px-3 py-2.5 rounded-lg ${
                message.type === 'error'
                  ? 'bg-red-500/6 text-red-400'
                  : message.type === 'info'
                  ? 'bg-brand-500/6 text-brand-400'
                  : 'bg-emerald-500/6 text-emerald-400'
              }`}
            >
              {message.type === 'info' && !generating ? (
                <span className="inline-flex items-center gap-1.5">
                  <RefreshCw size={12} className="animate-spin" />
                  {message.text}
                </span>
              ) : (
                message.text
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.form>

      {/* Clear Failed Banner */}
      <AnimatePresence>
        {failedCount > 0 && !loading && (
          <motion.div
            initial={{ opacity: 0, y: -6, height: 0 }}
            animate={{ opacity: 1, y: 0, height: 'auto' }}
            exit={{ opacity: 0, y: -6, height: 0 }}
            transition={{ duration: 0.2, ease }}
            className="mt-4 flex items-center justify-between gap-3 px-4 py-3 rounded-xl bg-red-500/6 border border-red-500/10"
          >
            <div className="flex items-center gap-2 min-w-0">
              <AlertTriangle size={14} className="text-red-400 shrink-0" />
              <span className="text-xs text-red-400">
                {failedCount} failed video{failedCount === 1 ? '' : 's'} — these don't count toward your plan limit.
              </span>
            </div>
            <button
              onClick={handleClearFailed}
              disabled={clearingFailed}
              className="shrink-0 flex items-center gap-1.5 text-xs font-medium text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/15 px-3 py-1.5 rounded-lg transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Trash2 size={12} className={clearingFailed ? 'animate-spin' : ''} />
              {clearingFailed ? 'Clearing…' : 'Clear All Failed'}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Video List */}
      {loading ? (
        <SkeletonVideoList />
      ) : videos.length === 0 ? (
        <EmptyState
          icon={Sparkles}
          title="No videos yet"
          description="Use the form above to create your first video. It takes about 2–3 minutes."
        />
      ) : (
        <StaggerContainer className="card" staggerDelay={0.03} data-tour="video-list">
          {videos.map((video) => {
            const cfg = statusConfig[video.status] || statusConfig.pending;
            const StatusIcon = cfg.icon;
            const isActiveJob = video.id === activeJobId;
            const canDownload = video.file_path && (video.status === 'completed' || video.status === 'posted');
            const canRegenerate = video.status === 'failed' || video.status === 'completed' || video.status === 'posted';

            return (
              <StaggerItem key={video.id}>
                <div className="px-5 py-4.5 transition-colors hover:bg-white/[0.02] duration-150">
                  <div className="flex items-center gap-4">
                    {/* Thumbnail placeholder */}
                    <div className="hidden sm:flex w-24 h-14 rounded-[10px] bg-surface-200 items-center justify-center shrink-0 overflow-hidden">
                      {video.status === 'generating' ? (
                        <RefreshCw size={16} className="text-brand-400/50 animate-spin" />
                      ) : (
                        <Video size={16} className="text-surface-500" />
                      )}
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">
                        {video.title || 'Untitled Video'}
                      </p>
                      <p className="text-[11px] text-surface-600 mt-1 truncate">
                        {video.topic}
                      </p>
                      {video.error_message && (
                        <p className="text-[11px] text-red-400 mt-1 truncate" title={video.error_message}>
                          {video.error_message}
                        </p>
                      )}
                    </div>

                    {/* Status badge */}
                    <span
                      className={`badge ${cfg.badge} flex items-center gap-1 shrink-0`}
                    >
                      {video.status === 'generating' ? (
                        <RefreshCw size={10} className="animate-spin" />
                      ) : (
                        <StatusIcon size={10} />
                      )}
                      {cfg.label}
                    </span>

                    {/* Action buttons */}
                    <div className="flex items-center gap-0.5 shrink-0">
                      {/* YouTube link */}
                      {video.youtube_url && (
                        <a
                          href={video.youtube_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-2 rounded text-brand-400 hover:bg-brand-500/10 transition-colors duration-150"
                          title="Watch on YouTube"
                        >
                          <ExternalLink size={14} />
                        </a>
                      )}

                      {/* Phase 6: Download MP4 button */}
                      {canDownload && (
                        <button
                          onClick={() => handleDownload(video.id, video.title)}
                          className="p-2 rounded text-blue-400 hover:bg-blue-500/10 transition-colors duration-150"
                          title="Download MP4"
                        >
                          <Download size={14} />
                        </button>
                      )}

                      {/* Phase 6: Regenerate button */}
                      {canRegenerate && (
                        <button
                          onClick={() => handleRegenerate(video.id)}
                          disabled={generating || regeneratingId === video.id}
                          className="p-2 rounded text-amber-400 hover:bg-amber-500/10 transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
                          title="Retry"
                        >
                          <RotateCcw size={14} className={regeneratingId === video.id ? 'animate-spin' : ''} />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Phase 6: Inline progress bar for the actively generating job */}
                  <AnimatePresence>
                    {isActiveJob && video.status === 'generating' && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="mt-2.5 sm:ml-28"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[10px] text-brand-400 font-medium flex items-center gap-1">
                            <RefreshCw size={9} className="animate-spin" />
                            {progressStep || 'Starting…'}
                          </span>
                          <span className="text-[10px] text-surface-600 tabular-nums">
                            {progressPct}%
                            {pipelineStartedAt && progressPct > 0 && (
                              <> · {estimateTimeRemaining(progressPct, pipelineStartedAt)}</>
                            )}
                          </span>
                        </div>
                        <div className="h-[3px] rounded-full bg-surface-200 overflow-hidden">
                          <motion.div
                            className="h-full rounded-full bg-brand-500"
                            animate={{ width: `${Math.min(100, progressPct || 0)}%` }}
                            transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
                          />
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </StaggerItem>
            );
          })}
        </StaggerContainer>
      )}
      </>
      )}
    </FadeIn>
  );
}
