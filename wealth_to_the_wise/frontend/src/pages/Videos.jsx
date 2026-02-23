import { useState } from 'react';
import {
  CheckCircle,
  XCircle,
  Clock,
  Upload,
  AlertTriangle,
  Film,
  CheckCheck,
} from 'lucide-react';

const initialVideos = [
  {
    id: 1,
    title: 'Why Budgeting Fails (And What Works)',
    thumbnail: null,
    status: 'pending',
    scheduledFor: '2025-01-20 18:00',
  },
  {
    id: 2,
    title: 'The Truth About Index Funds',
    thumbnail: null,
    status: 'pending',
    scheduledFor: '2025-01-21 18:00',
  },
  {
    id: 3,
    title: '7 Money Rules Rich People Follow',
    thumbnail: null,
    status: 'scheduled',
    scheduledFor: '2025-01-22 18:00',
  },
  {
    id: 4,
    title: 'How to Invest With $100',
    thumbnail: null,
    status: 'posted',
    scheduledFor: '2025-01-19 18:00',
  },
  {
    id: 5,
    title: 'Credit Score Myths Debunked',
    thumbnail: null,
    status: 'failed',
    scheduledFor: '2025-01-18 18:00',
  },
];

const statusConfig = {
  pending: { label: 'Pending', color: 'bg-amber-500/15 text-amber-400', icon: Clock },
  scheduled: { label: 'Scheduled', color: 'bg-brand-500/15 text-brand-400', icon: Clock },
  posted: { label: 'Posted', color: 'bg-emerald-500/15 text-emerald-400', icon: Upload },
  failed: { label: 'Failed', color: 'bg-red-500/15 text-red-400', icon: AlertTriangle },
};

export default function Videos() {
  const [videos, setVideos] = useState(initialVideos);

  function approve(id) {
    setVideos((prev) =>
      prev.map((v) => (v.id === id ? { ...v, status: 'scheduled' } : v))
    );
  }

  function reject(id) {
    setVideos((prev) => prev.filter((v) => v.id !== id));
  }

  function approveAll() {
    setVideos((prev) =>
      prev.map((v) => (v.status === 'pending' ? { ...v, status: 'scheduled' } : v))
    );
  }

  const hasPending = videos.some((v) => v.status === 'pending');

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Video Queue</h1>
          <p className="text-sm text-surface-700 mt-1">
            Review and approve generated videos before they go live
          </p>
        </div>

        {hasPending && (
          <button
            onClick={approveAll}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium bg-brand-600 text-white hover:bg-brand-700 transition-colors"
          >
            <CheckCheck size={16} />
            Approve All
          </button>
        )}
      </div>

      {/* Video List */}
      <div className="bg-surface-100 border border-surface-300 rounded-xl divide-y divide-surface-300">
        {videos.length === 0 && (
          <div className="px-5 py-12 text-center text-surface-600 text-sm">
            No videos in the queue. Start your automation to generate content.
          </div>
        )}

        {videos.map((video) => {
          const cfg = statusConfig[video.status];
          const StatusIcon = cfg.icon;

          return (
            <div key={video.id} className="flex items-center gap-4 px-5 py-4">
              {/* Thumbnail placeholder */}
              <div className="w-28 h-16 rounded-lg bg-surface-200 flex items-center justify-center shrink-0 overflow-hidden">
                {video.thumbnail ? (
                  <img
                    src={video.thumbnail}
                    alt=""
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <Film size={20} className="text-surface-500" />
                )}
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-surface-900 truncate">
                  {video.title}
                </p>
                <p className="text-xs text-surface-600 mt-1">
                  Scheduled: {video.scheduledFor}
                </p>
              </div>

              {/* Status badge */}
              <span
                className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full shrink-0 ${cfg.color}`}
              >
                <StatusIcon size={12} />
                {cfg.label}
              </span>

              {/* Actions */}
              {video.status === 'pending' && (
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => approve(video.id)}
                    className="p-2 rounded-lg text-emerald-400 hover:bg-emerald-500/15 transition-colors"
                    title="Approve"
                  >
                    <CheckCircle size={18} />
                  </button>
                  <button
                    onClick={() => reject(video.id)}
                    className="p-2 rounded-lg text-red-400 hover:bg-red-500/15 transition-colors"
                    title="Reject"
                  >
                    <XCircle size={18} />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
