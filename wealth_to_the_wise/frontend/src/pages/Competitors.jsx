import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonStatCards } from '../components/Skeleton';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import {
  Eye, Plus, Trash2, X, Users, Play, Film, TrendingUp, TrendingDown, Minus, ExternalLink,
} from 'lucide-react';

function formatNumber(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n?.toLocaleString() ?? '0';
}

export default function Competitors() {
  const [competitors, setCompetitors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ youtube_channel_id: '', name: '' });
  const [adding, setAdding] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [snapshots, setSnapshots] = useState({});

  const fetchCompetitors = useCallback(async () => {
    try {
      const res = await api.get('/competitors');
      setCompetitors(res.data.competitors || []);
    } catch { /* empty */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchCompetitors(); }, [fetchCompetitors]);

  const addCompetitor = async () => {
    if (!form.youtube_channel_id.trim() || !form.name.trim()) return;
    setAdding(true);
    try {
      await api.post('/competitors', {
        youtube_channel_id: form.youtube_channel_id.trim(),
        name: form.name.trim(),
      });
      setForm({ youtube_channel_id: '', name: '' });
      setShowAdd(false);
      fetchCompetitors();
    } catch { /* empty */ } finally {
      setAdding(false);
    }
  };

  const removeCompetitor = async (id) => {
    if (!confirm('Remove this competitor?')) return;
    try {
      await api.delete(`/competitors/${id}`);
      fetchCompetitors();
    } catch { /* empty */ }
  };

  const toggleExpand = async (id) => {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    if (!snapshots[id]) {
      try {
        const res = await api.get(`/competitors/${id}/snapshots`);
        setSnapshots((prev) => ({ ...prev, [id]: res.data.snapshots || [] }));
      } catch { /* empty */ }
    }
  };

  if (loading) return <div className="max-w-5xl mx-auto"><SkeletonStatCards /></div>;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <PageHeader
        title="Competitors"
        subtitle="Monitor competitor channels and track their growth"
        action={
          <button onClick={() => setShowAdd(true)}
            className="btn-primary flex items-center gap-2 text-[13px]">
            <Plus size={16} /> Track Competitor
          </button>
        }
      />

      {/* Add modal */}
      <AnimatePresence>
        {showAdd && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setShowAdd(false)}>
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="card !rounded-[20px] p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-white font-semibold">Track Competitor</h2>
                <button onClick={() => setShowAdd(false)} className="text-surface-600 hover:text-white"><X size={18} /></button>
              </div>
              <div className="space-y-3">
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Channel name (e.g., Graham Stephan)"
                  className="input-field" />
                <input value={form.youtube_channel_id} onChange={(e) => setForm({ ...form, youtube_channel_id: e.target.value })}
                  placeholder="YouTube Channel ID (e.g., UCGy7SkBjcIAgTiwkXEtPnYg)"
                  className="input-field" />
              </div>
              <div className="flex gap-3 mt-4">
                <button onClick={() => setShowAdd(false)} className="btn-secondary flex-1 text-[13px]">Cancel</button>
                <button onClick={addCompetitor} disabled={adding || !form.name.trim() || !form.youtube_channel_id.trim()}
                  className="btn-primary flex-1 text-[13px] disabled:opacity-50">
                  {adding ? 'Adding…' : 'Add'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Competitor list */}
      {competitors.length === 0 ? (
        <EmptyState icon={Eye} title="No competitors tracked"
          description="Add competitor YouTube channels to monitor their growth and content strategy."
          action={<button onClick={() => setShowAdd(true)} className="btn-primary text-[13px]">Track Competitor</button>} />
      ) : (
        <StaggerContainer className="space-y-3">
          {competitors.map((c) => (
            <StaggerItem key={c.id}>
              <div className="card overflow-hidden">
                <div className="p-5 flex items-center justify-between cursor-pointer hover:bg-white/[0.01] transition-colors"
                  onClick={() => toggleExpand(c.id)}>
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-xl bg-red-500/15 flex items-center justify-center">
                      <Play size={16} className="text-red-400" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-white text-[14px] font-medium">{c.name}</span>
                        {!c.is_active && <span className="px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 text-[10px]">INACTIVE</span>}
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-surface-600 text-[12px]">{c.youtube_channel_id}</span>
                        {c.subscriber_count && <span className="text-surface-600 text-[12px]">{formatNumber(c.subscriber_count)} subs</span>}
                        <a href={`https://youtube.com/channel/${c.youtube_channel_id}`} target="_blank" rel="noreferrer"
                          className="text-surface-600 hover:text-brand-400 text-[11px] flex items-center gap-0.5"
                          onClick={(e) => e.stopPropagation()}>
                          <ExternalLink size={10} /> View
                        </a>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button onClick={(e) => { e.stopPropagation(); removeCompetitor(c.id); }}
                      className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-red-400 transition-colors">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>

                {/* Snapshots */}
                <AnimatePresence>
                  {expanded === c.id && (
                    <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
                      className="overflow-hidden border-t border-white/[0.04]">
                      <div className="p-5 space-y-3">
                        {!snapshots[c.id] || snapshots[c.id].length === 0 ? (
                          <p className="text-surface-600 text-[13px] text-center py-4">No snapshots yet. The competitor worker will collect data on a regular schedule.</p>
                        ) : (
                          snapshots[c.id].slice(0, 5).map((s) => (
                            <div key={s.id} className="bg-white/[0.02] rounded-xl p-4 grid grid-cols-2 sm:grid-cols-5 gap-3">
                              <div>
                                <p className="text-surface-600 text-[10px]">Date</p>
                                <p className="text-white text-[13px] font-medium">{s.snapshot_date}</p>
                              </div>
                              <div>
                                <p className="text-surface-600 text-[10px]">Subscribers</p>
                                <p className="text-white text-[13px] font-medium">{formatNumber(s.subscriber_count)}</p>
                              </div>
                              <div>
                                <p className="text-surface-600 text-[10px]">Total Views</p>
                                <p className="text-white text-[13px] font-medium">{formatNumber(s.total_views)}</p>
                              </div>
                              <div>
                                <p className="text-surface-600 text-[10px]">Videos</p>
                                <p className="text-white text-[13px] font-medium">{s.video_count}</p>
                              </div>
                              <div>
                                <p className="text-surface-600 text-[10px]">Avg Views</p>
                                <p className="text-white text-[13px] font-medium">{formatNumber(s.avg_views_per_video)}</p>
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </StaggerItem>
          ))}
        </StaggerContainer>
      )}
    </div>
  );
}
