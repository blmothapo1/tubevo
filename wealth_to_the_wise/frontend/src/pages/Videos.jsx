import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../lib/api';
import Spinner from '../components/Spinner';
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
} from 'lucide-react';

const statusConfig = {
  pending: { label: 'Pending', color: 'bg-amber-500/15 text-amber-400', icon: Clock },
  generating: { label: 'Generating…', color: 'bg-brand-500/15 text-brand-400', icon: Film },
  completed: { label: 'Completed', color: 'bg-blue-500/15 text-blue-400', icon: CheckCircle },
  posted: { label: 'Posted', color: 'bg-emerald-500/15 text-emerald-400', icon: Upload },
  failed: { label: 'Failed', color: 'bg-red-500/15 text-red-400', icon: AlertTriangle },
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
        if (data.status === 'generating') {
          // Still running — keep polling
          return;
        }
        // Job finished — stop polling and update UI
        clearInterval(pollRef.current);
        pollRef.current = null;
        setActiveJobId(null);
        setGenerating(false);

        if (data.status === 'failed') {
          setMessage({
            type: 'error',
            text: data.error_message || 'Video generation failed.',
          });
        } else if (data.status === 'posted') {
          setMessage({
            type: 'success',
            text: `Video "${data.title}" generated and posted to YouTube!`,
          });
        } else {
          setMessage({
            type: 'success',
            text: `Video "${data.title}" generated successfully!`,
          });
        }
        fetchVideos();
      } catch {
        // Network error — keep polling
      }
    }

    // Poll every 5 seconds
    pollRef.current = setInterval(pollStatus, 5000);
    // Also poll immediately
    pollStatus();

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
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
        // Pipeline running in background — start polling
        setActiveJobId(data.video_id);
        setMessage({
          type: 'info',
          text: data.message,
        });
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner className="w-8 h-8" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold text-white">Videos</h1>
        <p className="text-sm text-surface-700 mt-1">
          Generate new videos and track their status
        </p>
      </div>

      {/* Generate Form */}
      <form
        onSubmit={handleGenerate}
        className="bg-surface-100 border border-surface-300 rounded-xl p-5"
      >
        <h3 className="text-sm font-medium text-surface-800 mb-3">Generate a New Video</h3>
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Enter a topic, e.g. 'Why Budgeting Fails'"
            className="flex-1 px-4 py-2.5 rounded-lg bg-surface-200 border border-surface-300 text-surface-900 text-sm placeholder-surface-500 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500"
            disabled={generating}
          />
          <button
            type="submit"
            disabled={generating}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium gradient-brand text-white hover:opacity-90 transition-all disabled:opacity-50 glow-brand"
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
          </button>
        </div>
        {message.text && (
          <div
            className={`mt-3 text-sm px-4 py-2.5 rounded-lg ${
              message.type === 'error'
                ? 'bg-red-500/10 border border-red-500/20 text-red-400'
                : message.type === 'info'
                ? 'bg-brand-500/10 border border-brand-500/20 text-brand-400'
                : 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
            }`}
          >
            {message.type === 'info' && (
              <span className="inline-flex items-center gap-2">
                <RefreshCw size={14} className="animate-spin" />
                {message.text}
              </span>
            )}
            {message.type !== 'info' && message.text}
          </div>
        )}
      </form>

      {/* Video List */}
      <div className="bg-surface-100 border border-surface-300 rounded-xl divide-y divide-surface-300">
        {videos.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <Sparkles size={32} className="text-surface-500 mx-auto mb-3" />
            <p className="text-sm text-surface-600">
              No videos yet. Use the form above to generate your first video!
            </p>
          </div>
        ) : (
          videos.map((video) => {
            const cfg = statusConfig[video.status] || statusConfig.pending;
            const StatusIcon = cfg.icon;

            return (
              <div key={video.id} className="flex items-center gap-4 px-5 py-4">
                {/* Thumbnail placeholder */}
                <div className="hidden sm:flex w-28 h-16 rounded-lg bg-surface-200 items-center justify-center shrink-0 overflow-hidden border border-surface-300">
                  {video.status === 'generating' ? (
                    <RefreshCw size={20} className="text-brand-400/60 animate-spin" />
                  ) : (
                    <Film size={20} className="text-brand-400/60" />
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-surface-900 truncate">
                    {video.title}
                  </p>
                  <p className="text-xs text-surface-600 mt-1">
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
                  className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full shrink-0 ${cfg.color}`}
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
                  <a
                    href={video.youtube_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2 rounded-lg text-brand-400 hover:bg-brand-500/15 transition-colors shrink-0"
                    title="Watch on YouTube"
                  >
                    <ExternalLink size={16} />
                  </a>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
