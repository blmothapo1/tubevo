import { useState, useEffect } from 'react';
import api from '../lib/api';
import Spinner from '../components/Spinner';
import { ExternalLink, CalendarDays, Sparkles } from 'lucide-react';

export default function Schedule() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetch() {
      try {
        const { data } = await api.get('/api/videos/history');
        // Only show posted / completed videos in "Post History"
        setHistory(data.filter((v) => v.status === 'posted' || v.youtube_url));
      } catch {
        // keep empty
      } finally {
        setLoading(false);
      }
    }
    fetch();
  }, []);

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
        <h1 className="text-2xl font-semibold text-white">Post History</h1>
        <p className="text-sm text-surface-700 mt-1">
          Videos that have been posted to your YouTube channel
        </p>
      </div>

      {/* Table */}
      <div className="bg-surface-100 border border-surface-300 rounded-xl overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-surface-300">
              <th className="px-5 py-3 text-xs font-medium text-surface-600 uppercase tracking-wider">
                Title
              </th>
              <th className="px-5 py-3 text-xs font-medium text-surface-600 uppercase tracking-wider">
                Posted
              </th>
              <th className="px-5 py-3 text-xs font-medium text-surface-600 uppercase tracking-wider text-right">
                Link
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-300">
            {history.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-5 py-12 text-center">
                  <Sparkles size={32} className="text-surface-500 mx-auto mb-3" />
                  <p className="text-sm text-surface-600">
                    No videos posted yet. Generate and post your first video!
                  </p>
                </td>
              </tr>
            ) : (
              history.map((item) => (
                <tr key={item.id} className="hover:bg-surface-200/50 transition-colors">
                  <td className="px-5 py-4">
                    <p className="text-sm font-medium text-surface-900 truncate max-w-xs">
                      {item.title}
                    </p>
                  </td>
                  <td className="px-5 py-4">
                    <span className="flex items-center gap-1.5 text-sm text-surface-700">
                      <CalendarDays size={14} className="text-surface-600" />
                      {item.created_at
                        ? new Date(item.created_at).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : '—'}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    {item.youtube_url ? (
                      <a
                        href={item.youtube_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-sm text-brand-400 hover:text-brand-300 transition-colors"
                      >
                        Watch <ExternalLink size={14} />
                      </a>
                    ) : (
                      <span className="text-xs text-surface-500">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
