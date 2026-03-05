import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonStatCards } from '../components/Skeleton';
import {
  Mic, Plus, Trash2, X, RefreshCw, CheckCircle2, Clock, AlertTriangle, Loader2,
} from 'lucide-react';

const STATUS_STYLES = {
  pending: { icon: Clock, color: 'text-amber-400', bg: 'bg-amber-500/15', label: 'Pending' },
  processing: { icon: Loader2, color: 'text-blue-400', bg: 'bg-blue-500/15', label: 'Processing' },
  ready: { icon: CheckCircle2, color: 'text-emerald-400', bg: 'bg-emerald-500/15', label: 'Ready' },
  failed: { icon: AlertTriangle, color: 'text-red-400', bg: 'bg-red-500/15', label: 'Failed' },
};

export default function VoiceClones() {
  const [clones, setClones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', description: '' });
  const [creating, setCreating] = useState(false);

  const fetchClones = useCallback(async () => {
    try {
      const res = await api.get('/voice-clones');
      setClones(res.data.voice_clones || []);
    } catch { /* empty */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchClones(); }, [fetchClones]);

  const createClone = async () => {
    if (!form.name.trim()) return;
    setCreating(true);
    try {
      await api.post('/voice-clones', {
        name: form.name.trim(),
        description: form.description.trim() || null,
      });
      setForm({ name: '', description: '' });
      setShowCreate(false);
      fetchClones();
    } catch { /* empty */ } finally {
      setCreating(false);
    }
  };

  const deleteClone = async (id) => {
    if (!confirm('Delete this voice clone?')) return;
    try {
      await api.delete(`/voice-clones/${id}`);
      fetchClones();
    } catch { /* empty */ }
  };

  const retryClone = async (id) => {
    try {
      await api.post(`/voice-clones/${id}/retry`);
      fetchClones();
    } catch { /* empty */ }
  };

  if (loading) return <div className="max-w-4xl mx-auto"><SkeletonStatCards /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <FadeIn>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white">Voice Clones</h1>
            <p className="text-surface-600 text-[13px] mt-1">Create and manage AI voice clones for your videos</p>
          </div>
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-[13px] font-medium transition-colors">
            <Plus size={16} /> New Voice
          </button>
        </div>
      </FadeIn>

      {/* Create modal */}
      <AnimatePresence>
        {showCreate && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setShowCreate(false)}>
            <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.95, opacity: 0 }}
              className="glass rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-white font-semibold">New Voice Clone</h2>
                <button onClick={() => setShowCreate(false)} className="text-surface-600 hover:text-white"><X size={18} /></button>
              </div>
              <div className="space-y-3">
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Voice name (e.g., Professional Male)"
                  className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.06] text-white text-[13px] placeholder:text-surface-600 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
                  onKeyDown={(e) => e.key === 'Enter' && createClone()} />
                <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Description (optional)"
                  rows={3}
                  className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.06] text-white text-[13px] placeholder:text-surface-600 focus:outline-none focus:ring-1 focus:ring-brand-500/50 resize-none" />
              </div>
              <div className="flex gap-3 mt-4">
                <button onClick={() => setShowCreate(false)} className="flex-1 py-2.5 rounded-xl border border-white/[0.06] text-surface-700 text-[13px] font-medium hover:bg-white/[0.02]">Cancel</button>
                <button onClick={createClone} disabled={creating || !form.name.trim()}
                  className="flex-1 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-[13px] font-medium disabled:opacity-50 transition-colors">
                  {creating ? 'Creating…' : 'Create'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Clone list */}
      {clones.length === 0 ? (
        <FadeIn>
          <div className="glass rounded-2xl p-12 text-center">
            <Mic size={40} className="mx-auto text-surface-600 mb-4" />
            <p className="text-white font-medium mb-1">No voice clones yet</p>
            <p className="text-surface-600 text-[13px]">Create your first AI voice clone to use in video generation.</p>
          </div>
        </FadeIn>
      ) : (
        <StaggerContainer className="space-y-3">
          {clones.map((clone) => {
            const style = STATUS_STYLES[clone.status] || STATUS_STYLES.pending;
            const StatusIcon = style.icon;
            return (
              <StaggerItem key={clone.id}>
                <div className="glass rounded-2xl p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${style.bg}`}>
                        <StatusIcon size={18} className={`${style.color} ${clone.status === 'processing' ? 'animate-spin' : ''}`} />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-white text-[14px] font-medium">{clone.name}</span>
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${style.bg} ${style.color}`}>{style.label}</span>
                        </div>
                        {clone.description && (
                          <p className="text-surface-600 text-[12px] mt-0.5 max-w-md">{clone.description}</p>
                        )}
                        <div className="flex items-center gap-3 mt-1.5">
                          {clone.elevenlabs_voice_id && (
                            <span className="text-surface-600 text-[11px]">EL ID: {clone.elevenlabs_voice_id.slice(0, 12)}…</span>
                          )}
                          {clone.sample_duration_secs && (
                            <span className="text-surface-600 text-[11px]">{clone.sample_duration_secs}s sample</span>
                          )}
                          <span className="text-surface-600 text-[11px]">
                            {new Date(clone.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        {clone.error_message && (
                          <p className="text-red-400 text-[12px] mt-2 bg-red-500/10 px-3 py-1.5 rounded-lg">{clone.error_message}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {clone.preview_url && (
                        <a href={clone.preview_url} target="_blank" rel="noreferrer"
                          className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-brand-400 transition-colors" title="Preview">
                          <Mic size={16} />
                        </a>
                      )}
                      {clone.status === 'failed' && (
                        <button onClick={() => retryClone(clone.id)} title="Retry"
                          className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-amber-400 transition-colors">
                          <RefreshCw size={16} />
                        </button>
                      )}
                      <button onClick={() => deleteClone(clone.id)} title="Delete"
                        className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-red-400 transition-colors">
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                </div>
              </StaggerItem>
            );
          })}
        </StaggerContainer>
      )}
    </div>
  );
}
