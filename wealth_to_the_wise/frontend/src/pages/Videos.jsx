import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonVideoList } from '../components/Skeleton';
import ConfettiCelebration from '../components/ConfettiCelebration';
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
} from 'lucide-react';

const ease = [0.25, 0.1, 0.25, 1];

const statusConfig = {
  pending:    { label: 'Pending',      color: 'bg-amber-500/15 text-amber-400',     icon: Clock },
  generating: { label: 'Generating…',  color: 'bg-brand-500/15 text-brand-400',     icon: Film },
  completed:  { label: 'Completed',    color: 'bg-blue-500/15 text-blue-400',        icon: CheckCircle },
  posted:     { label: 'Posted',       color: 'bg-emerald-500/15 text-emerald-400', icon: Upload },
  failed:     { label: 'Failed',       color: 'bg-red-500/15 text-red-400',           icon: AlertTriangle },
};

// ── Pipeline step labels for ETA estimation ──
const PIPELINE_STEPS = [
  { label: 'Generating script', pctStart: 0, pctEnd: 15 },
  { label: 'Generating metadata', pctStart: 15, pctEnd: 22 },
  { label: 'Generating voiceover', pctStart: 22, pctEnd: 38 },
  { label: 'Planning scenes', pctStart: 38, pctEnd: 45 },
  { label: 'Downloading footage', pctStart: 45, pctEnd: 60 },
  { label: 'Building video', pctStart: 60, pctEnd: 78 },
  { label: 'Generating thumbnail', pctStart: 78, pctEnd: 85 },
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
      <div className="h-1.5 rounded-sm bg-surface-200 overflow-hidden">
        <motion.div
          className="h-full rounded-sm bg-brand-500"
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
  useEffect(() => {
    if (!activeJobId) return;

    async function pollStatus() {
      try {
        const { data } = await api.get(`/api/videos/${activeJobId}/status`);

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
          setMessage({ type: 'error', text: data.error_message || 'Video generation failed.' });
        } else if (data.status === 'posted') {
          setMessage({ type: 'success', text: `Video "${data.title}" generated and posted to YouTube!` });
          triggerFirstVideoConfetti();
        } else {
          setMessage({ type: 'success', text: `Video "${data.title}" generated successfully!` });
          triggerFirstVideoConfetti();
        }
        fetchVideos();
      } catch {
        // Network error — keep polling
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
      setMessage({ type: 'error', text: 'This topic is already being generated. Please wait for it to finish.' });
      return;
    }

    setGenerating(true);
    setMessage({ type: '', text: '' });
    setProgressPct(0);
    setProgressStep('Starting…');

    try {
      const { data } = await api.post('/api/videos/generate', { topic: topic.trim() });

      if (data.status === 'generating' && data.video_id) {
        setActiveJobId(data.video_id);
        setPipelineStartedAt(Date.now() / 1000);
        setMessage({ type: 'info', text: data.message });
        setTopic('');
        fetchVideos();
      } else if (data.status === 'failed') {
        setMessage({ type: 'error', text: data.message });
        setGenerating(false);
        setProgressStep('');
      } else {
        setMessage({ type: 'success', text: data.message });
        setTopic('');
        setGenerating(false);
        setProgressStep('');
        fetchVideos();
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 429) {
        setMessage({ type: 'error', text: 'Rate limit reached. Try again later.' });
      } else if (err.response?.status === 403) {
        setMessage({ type: 'error', text: detail || 'You have reached your plan limit this month.' });
      } else {
        setMessage({ type: 'error', text: detail || 'Generation failed.' });
      }
      setGenerating(false);
      setProgressStep('');
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
      setMessage({ type: 'error', text: detail || 'Regeneration failed.' });
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
    <FadeIn className="max-w-5xl mx-auto space-y-5 sm:space-y-6">
      {/* Confetti on first successful video — additive */}
      <ConfettiCelebration show={showConfetti} onDone={() => setShowConfetti(false)} />

      {/* Header + Queue Indicator */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-white tracking-tight">Videos</h1>
          <p className="text-xs text-surface-600 mt-1 uppercase tracking-wider font-medium">
            Generate & track AI-powered videos
          </p>
        </div>

        {/* Phase 6: Render Queue Indicator */}
        <AnimatePresence>
          {queueInfo && queueInfo.global_generating > 0 && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-brand-500/6 shrink-0"
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

      {/* Generate Form */}
      <motion.form
        onSubmit={handleGenerate}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.1, ease }}
        className="card p-5 sm:p-6"
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded bg-brand-500 flex items-center justify-center">
            <Wand2 size={16} className="text-white" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">Generate a New Video</h3>
            <p className="text-[11px] text-surface-600">Enter a topic and we'll create a full video with AI</p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-2.5">
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
                Generating…
              </>
            ) : (
              <>
                <Send size={14} />
                Generate
              </>
            )}
          </motion.button>
        </div>

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

      {/* Video List */}
      {loading ? (
        <SkeletonVideoList />
      ) : videos.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.2, ease }}
          className="card px-5 py-10 sm:p-10 text-center"
          data-tour="video-list"
        >
          <div className="w-14 h-14 rounded bg-brand-500/10 flex items-center justify-center mx-auto mb-3">
            <Sparkles size={24} className="text-brand-400" />
          </div>
          <h3 className="text-sm font-semibold text-white mb-1.5">No videos yet</h3>
          <p className="text-xs text-surface-600 max-w-sm mx-auto">
            Use the form above to generate your first AI-powered video. It takes about 2–3 minutes.
          </p>
        </motion.div>
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
                <div className="px-4 py-3.5 sm:px-5 sm:py-4 transition-colors hover:bg-surface-200/30 duration-150">
                  <div className="flex items-center gap-3">
                    {/* Thumbnail placeholder */}
                    <div className="hidden sm:flex w-24 h-14 rounded-lg bg-surface-200 items-center justify-center shrink-0 overflow-hidden">
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
                      <p className="text-[11px] text-surface-600 mt-0.5 truncate">
                        {video.topic}
                      </p>
                      {video.error_message && (
                        <p className="text-[11px] text-red-400 mt-0.5 truncate" title={video.error_message}>
                          {video.error_message}
                        </p>
                      )}
                    </div>

                    {/* Status badge */}
                    <span
                      className={`flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-lg shrink-0 uppercase tracking-wider ${cfg.color}`}
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
                          title="Regenerate"
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
                        <div className="h-1 rounded-sm bg-surface-200 overflow-hidden">
                          <motion.div
                            className="h-full rounded-sm bg-brand-500"
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
    </FadeIn>
  );
}
