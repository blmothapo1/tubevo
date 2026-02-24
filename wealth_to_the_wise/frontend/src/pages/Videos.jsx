import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonVideoList } from '../components/Skeleton';
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
} from 'lucide-react';

const ease = [0.25, 0.1, 0.25, 1];

const statusConfig = {
  pending:    { label: 'Pending',      color: 'bg-amber-500/15 text-amber-400 border-amber-500/20',     icon: Clock },
  generating: { label: 'Generating…',  color: 'bg-brand-500/15 text-brand-400 border-brand-500/20',     icon: Film },
  completed:  { label: 'Completed',    color: 'bg-blue-500/15 text-blue-400 border-blue-500/20',        icon: CheckCircle },
  posted:     { label: 'Posted',       color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20', icon: Upload },
  failed:     { label: 'Failed',       color: 'bg-red-500/15 text-red-400 border-red-500/20',           icon: AlertTriangle },
};

export default function Videos() {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [topic, setTopic] = useState('');
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [activeJobId, setActiveJobId] = useState(null);
  const pollRef = useRef(null);

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

  // ── Poll for status when a job is active ──
  useEffect(() => {
    if (!activeJobId) return;

    async function pollStatus() {
      try {
        const { data } = await api.get(`/api/videos/${activeJobId}/status`);
        if (data.status === 'generating') return;

        clearInterval(pollRef.current);
        pollRef.current = null;
        setActiveJobId(null);
        setGenerating(false);

        if (data.status === 'failed') {
          setMessage({ type: 'error', text: data.error_message || 'Video generation failed.' });
        } else if (data.status === 'posted') {
          setMessage({ type: 'success', text: `Video "${data.title}" generated and posted to YouTube!` });
        } else {
          setMessage({ type: 'success', text: `Video "${data.title}" generated successfully!` });
        }
        fetchVideos();
      } catch {
        // Network error — keep polling
      }
    }

    pollRef.current = setInterval(pollStatus, 5000);
    pollStatus();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeJobId, fetchVideos]);

  async function handleGenerate(e) {
    e.preventDefault();
    if (!topic.trim() || topic.trim().length < 3) {
      setMessage({ type: 'error', text: 'Topic must be at least 3 characters.' });
      return;
    }

    setGenerating(true);
    setMessage({ type: '', text: '' });

    try {
      const { data } = await api.post('/api/videos/generate', { topic: topic.trim() });

      if (data.status === 'generating' && data.video_id) {
        setActiveJobId(data.video_id);
        setMessage({ type: 'info', text: data.message });
        setTopic('');
        fetchVideos();
      } else if (data.status === 'failed') {
        setMessage({ type: 'error', text: data.message });
        setGenerating(false);
      } else {
        setMessage({ type: 'success', text: data.message });
        setTopic('');
        setGenerating(false);
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
    }
  }

  return (
    <FadeIn className="max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Videos</h1>
        <p className="text-sm text-surface-600 mt-2">
          Generate AI-powered videos and track their progress
        </p>
      </div>

      {/* Generate Form */}
      <motion.form
        onSubmit={handleGenerate}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.1, ease }}
        className="card-elevated p-6 sm:p-8"
      >
        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-lg shadow-brand-500/20">
            <Wand2 size={20} className="text-white" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">Generate a New Video</h3>
            <p className="text-xs text-surface-600">Enter a topic and we'll create a full video with AI</p>
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
          />
          <motion.button
            type="submit"
            disabled={generating}
            whileHover={{ scale: 1.02, y: -1 }}
            whileTap={{ scale: 0.97 }}
            className="btn-primary flex items-center justify-center gap-2 px-6 py-3 whitespace-nowrap"
          >
            {generating ? (
              <>
                <RefreshCw size={16} className="animate-spin" />
                Generating…
              </>
            ) : (
              <>
                <Send size={16} />
                Generate
              </>
            )}
          </motion.button>
        </div>

        {/* Message Banner */}
        <AnimatePresence mode="wait">
          {message.text && (
            <motion.div
              key={message.text}
              initial={{ opacity: 0, y: -8, height: 0 }}
              animate={{ opacity: 1, y: 0, height: 'auto' }}
              exit={{ opacity: 0, y: -8, height: 0 }}
              transition={{ duration: 0.3, ease }}
              className={`mt-4 text-sm px-4 py-3 rounded-xl border ${
                message.type === 'error'
                  ? 'bg-red-500/8 border-red-500/20 text-red-400'
                  : message.type === 'info'
                  ? 'bg-brand-500/8 border-brand-500/20 text-brand-400'
                  : 'bg-emerald-500/8 border-emerald-500/20 text-emerald-400'
              }`}
            >
              {message.type === 'info' ? (
                <span className="inline-flex items-center gap-2">
                  <RefreshCw size={14} className="animate-spin" />
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
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.2, ease }}
          className="card-elevated p-12 text-center"
        >
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500/20 to-brand-600/10 flex items-center justify-center mx-auto mb-4">
            <Sparkles size={28} className="text-brand-400" />
          </div>
          <h3 className="text-base font-semibold text-white mb-2">No videos yet</h3>
          <p className="text-sm text-surface-600 max-w-sm mx-auto">
            Use the form above to generate your first AI-powered video. It takes about 2–3 minutes.
          </p>
        </motion.div>
      ) : (
        <StaggerContainer className="card-elevated divide-y divide-surface-300/30" staggerDelay={0.04}>
          {videos.map((video) => {
            const cfg = statusConfig[video.status] || statusConfig.pending;
            const StatusIcon = cfg.icon;

            return (
              <StaggerItem key={video.id}>
                <motion.div
                  className="flex items-center gap-4 px-5 py-4 sm:px-6 sm:py-5 transition-colors hover:bg-surface-200/30"
                  whileHover={{ x: 2 }}
                  transition={{ duration: 0.2, ease }}
                >
                  {/* Thumbnail placeholder */}
                  <div className="hidden sm:flex w-28 h-16 rounded-xl bg-surface-200/80 items-center justify-center shrink-0 overflow-hidden border border-surface-300/50">
                    {video.status === 'generating' ? (
                      <RefreshCw size={20} className="text-brand-400/60 animate-spin" />
                    ) : (
                      <Video size={20} className="text-surface-500" />
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">
                      {video.title || 'Untitled Video'}
                    </p>
                    <p className="text-xs text-surface-600 mt-1 truncate">
                      {video.topic}
                    </p>
                    {video.error_message && (
                      <p className="text-xs text-red-400 mt-1 truncate" title={video.error_message}>
                        {video.error_message}
                      </p>
                    )}
                  </div>

                  {/* Status badge */}
                  <span
                    className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full shrink-0 border ${cfg.color}`}
                  >
                    {video.status === 'generating' ? (
                      <RefreshCw size={12} className="animate-spin" />
                    ) : (
                      <StatusIcon size={12} />
                    )}
                    {cfg.label}
                  </span>

                  {/* YouTube link */}
                  {video.youtube_url && (
                    <motion.a
                      href={video.youtube_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-2.5 rounded-xl text-brand-400 hover:bg-brand-500/10 transition-colors shrink-0"
                      title="Watch on YouTube"
                      whileHover={{ scale: 1.1 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <ExternalLink size={16} />
                    </motion.a>
                  )}
                </motion.div>
              </StaggerItem>
            );
          })}
        </StaggerContainer>
      )}
    </FadeIn>
  );
}
