import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonVideoList } from '../components/Skeleton';
import { ExternalLink, CalendarDays, Sparkles, Upload, Play } from 'lucide-react';

const ease = [0.25, 0.1, 0.25, 1];

export default function Schedule() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetch() {
      try {
        const { data } = await api.get('/api/videos/history');
        setHistory(data.filter((v) => v.status === 'posted' || v.youtube_url));
      } catch {
        // keep empty
      } finally {
        setLoading(false);
      }
    }
    fetch();
  }, []);

  return (
    <FadeIn className="max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Post History</h1>
        <p className="text-sm text-surface-600 mt-2">
          Videos that have been posted to your YouTube channel
        </p>
      </div>

      {/* Content */}
      {loading ? (
        <SkeletonVideoList />
      ) : history.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.15, ease }}
          className="card-elevated p-12 text-center"
        >
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500/20 to-brand-600/10 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-brand-500/10">
            <Upload size={28} className="text-brand-400" />
          </div>
          <h3 className="text-base font-semibold text-white mb-2">No videos posted yet</h3>
          <p className="text-sm text-surface-600 max-w-sm mx-auto">
            Generate and post your first video — it'll show up here with a direct YouTube link.
          </p>
        </motion.div>
      ) : (
        <>
          {/* Desktop table */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1, ease }}
            className="hidden sm:block card-elevated overflow-hidden"
          >
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-surface-300/40">
                  <th className="px-6 py-4 text-xs font-medium text-surface-600 uppercase tracking-wider">
                    Title
                  </th>
                  <th className="px-6 py-4 text-xs font-medium text-surface-600 uppercase tracking-wider">
                    Posted
                  </th>
                  <th className="px-6 py-4 text-xs font-medium text-surface-600 uppercase tracking-wider text-right">
                    Link
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-300/30">
                {history.map((item, i) => (
                  <motion.tr
                    key={item.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: 0.05 * i, ease }}
                    className="group transition-colors hover:bg-surface-200/30"
                  >
                    <td className="px-6 py-5">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-brand-500/10 flex items-center justify-center shrink-0">
                          <Play size={14} className="text-brand-400" />
                        </div>
                        <p className="text-sm font-medium text-white truncate max-w-xs group-hover:text-brand-300 transition-colors">
                          {item.title}
                        </p>
                      </div>
                    </td>
                    <td className="px-6 py-5">
                      <span className="flex items-center gap-2 text-sm text-surface-700">
                        <CalendarDays size={14} className="text-brand-400" />
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
                    <td className="px-6 py-5 text-right">
                      {item.youtube_url ? (
                        <motion.a
                          href={item.youtube_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 text-sm text-brand-400 hover:text-brand-300 transition-colors font-medium"
                          whileHover={{ x: 2 }}
                        >
                          Watch <ExternalLink size={14} />
                        </motion.a>
                      ) : (
                        <span className="text-xs text-surface-500">—</span>
                      )}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </motion.div>

          {/* Mobile card list */}
          <StaggerContainer className="sm:hidden space-y-3" staggerDelay={0.05}>
            {history.map((item) => (
              <StaggerItem key={item.id}>
                <div className="card-elevated px-5 py-4 space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-brand-500/10 flex items-center justify-center shrink-0">
                      <Play size={14} className="text-brand-400" />
                    </div>
                    <p className="text-sm font-medium text-white truncate">{item.title}</p>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-xs text-surface-600">
                      <CalendarDays size={12} className="text-brand-400" />
                      {item.created_at
                        ? new Date(item.created_at).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            year: 'numeric',
                          })
                        : '—'}
                    </span>
                    {item.youtube_url ? (
                      <a
                        href={item.youtube_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-brand-400 hover:text-brand-300 transition-colors font-medium"
                      >
                        Watch <ExternalLink size={12} />
                      </a>
                    ) : (
                      <span className="text-xs text-surface-500">—</span>
                    )}
                  </div>
                </div>
              </StaggerItem>
            ))}
          </StaggerContainer>
        </>
      )}
    </FadeIn>
  );
}
