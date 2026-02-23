import { useState, useEffect, useCallback } from 'react';
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
} from 'lucide-react';

const statusConfig = {
  pending: { label: 'Pending', color: 'bg-amber-500/15 text-amber-400', icon: Clock },
  generating: { label: 'Generating', color: 'bg-brand-500/15 text-brand-400', icon: Film },
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
      setMessage({
        type: data.status === 'failed' ? 'error' : 'success',
        text: data.message,
      });
      setTopic('');
      fetchVideos();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 429) {
        setMessage({ type: 'error', text: 'Rate limit reached. Try again later.' });
      } else {
        setMessage({ type: 'error', text: detail || 'Generation failed.' });
      }
    } finally {
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
        <h1 className="text-2xl font-semibold text-white">Videos</h1>
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
        <div className="flex gap-3">
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
              <Spinner className="w-4 h-4" />
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
                : 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
            }`}
          >
            {message.text}
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
                <div className="w-28 h-16 rounded-lg bg-surface-200 flex items-center justify-center shrink-0 overflow-hidden border border-surface-300">
                  <Film size={20} className="text-brand-400/60" />
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-surface-900 truncate">
                    {video.title}
                  </p>
                  <p className="text-xs text-surface-600 mt-1">
                    {video.topic}
                  </p>
                </div>

                {/* Status badge */}
                <span
                  className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full shrink-0 ${cfg.color}`}
                >
                  <StatusIcon size={12} />
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
