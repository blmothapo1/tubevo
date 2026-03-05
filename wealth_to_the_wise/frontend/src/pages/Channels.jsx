import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonStatCards } from '../components/Skeleton';
import {
  Tv2, Plus, Trash2, Star, Link2, Youtube, ExternalLink, X,
} from 'lucide-react';

export default function Channels() {
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  const fetchChannels = useCallback(async () => {
    try {
      const res = await api.get('/channels');
      setChannels(res.data.channels || []);
    } catch { /* empty */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchChannels(); }, [fetchChannels]);

  const createChannel = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await api.post('/channels', { name: newName.trim(), platform: 'youtube' });
      setNewName('');
      setShowCreate(false);
      fetchChannels();
    } catch { /* empty */ } finally {
      setCreating(false);
    }
  };

  const deleteChannel = async (id) => {
    if (!confirm('Delete this channel?')) return;
    try {
      await api.delete(`/channels/${id}`);
      fetchChannels();
    } catch { /* empty */ }
  };

  const setDefault = async (id) => {
    try {
      await api.post(`/channels/${id}/set-default`);
      fetchChannels();
    } catch { /* empty */ }
  };

  if (loading) return <div className="max-w-4xl mx-auto"><SkeletonStatCards /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <FadeIn>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white">Channels</h1>
            <p className="text-surface-600 text-[13px] mt-1">Manage your YouTube channels</p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-[13px] font-medium transition-colors"
          >
            <Plus size={16} /> Add Channel
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
                <h2 className="text-white font-semibold">New Channel</h2>
                <button onClick={() => setShowCreate(false)} className="text-surface-600 hover:text-white"><X size={18} /></button>
              </div>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Channel name"
                className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.06] text-white text-[13px] placeholder:text-surface-600 focus:outline-none focus:ring-1 focus:ring-brand-500/50"
                onKeyDown={(e) => e.key === 'Enter' && createChannel()}
              />
              <div className="flex gap-3 mt-4">
                <button onClick={() => setShowCreate(false)} className="flex-1 py-2.5 rounded-xl border border-white/[0.06] text-surface-700 text-[13px] font-medium hover:bg-white/[0.02]">Cancel</button>
                <button onClick={createChannel} disabled={creating || !newName.trim()}
                  className="flex-1 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-[13px] font-medium disabled:opacity-50 transition-colors">
                  {creating ? 'Creating…' : 'Create'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Channel list */}
      {channels.length === 0 ? (
        <FadeIn>
          <div className="glass rounded-2xl p-12 text-center">
            <Tv2 size={40} className="mx-auto text-surface-600 mb-4" />
            <p className="text-white font-medium mb-1">No channels yet</p>
            <p className="text-surface-600 text-[13px]">Add your first channel to get started with multi-channel management.</p>
          </div>
        </FadeIn>
      ) : (
        <StaggerContainer className="space-y-3">
          {channels.map((ch) => (
            <StaggerItem key={ch.id}>
              <div className="glass rounded-2xl p-5 flex items-center justify-between group">
                <div className="flex items-center gap-4">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${ch.is_default ? 'bg-brand-500/20' : 'bg-white/[0.04]'}`}>
                    {ch.youtube_connected ? <Youtube size={18} className="text-red-400" /> : <Tv2 size={18} className="text-surface-600" />}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-white text-[14px] font-medium">{ch.name}</span>
                      {ch.is_default && (
                        <span className="px-2 py-0.5 rounded-full bg-brand-500/20 text-brand-400 text-[10px] font-medium">DEFAULT</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="text-surface-600 text-[12px]">{ch.platform}</span>
                      {ch.channel_title && (
                        <span className="text-surface-600 text-[12px] flex items-center gap-1">
                          <Link2 size={10} /> {ch.channel_title}
                        </span>
                      )}
                      {ch.youtube_channel_id && (
                        <a href={`https://youtube.com/channel/${ch.youtube_channel_id}`} target="_blank" rel="noreferrer"
                          className="text-surface-600 hover:text-brand-400 text-[11px] flex items-center gap-0.5">
                          <ExternalLink size={10} /> View
                        </a>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  {!ch.is_default && (
                    <button onClick={() => setDefault(ch.id)} title="Set as default"
                      className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-amber-400 transition-colors">
                      <Star size={16} />
                    </button>
                  )}
                  <button onClick={() => deleteChannel(ch.id)} title="Delete"
                    className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-red-400 transition-colors">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            </StaggerItem>
          ))}
        </StaggerContainer>
      )}
    </div>
  );
}
