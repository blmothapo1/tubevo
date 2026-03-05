import { useState, useEffect, useCallback } from 'react';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonStatCards } from '../components/Skeleton';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import {
  Image, Beaker, Trophy, RotateCcw, XCircle, CheckCircle2, Clock, MousePointerClick,
} from 'lucide-react';

const STATUS_STYLES = {
  running: { icon: Beaker, color: 'text-blue-400', bg: 'bg-blue-500/15' },
  concluded: { icon: Trophy, color: 'text-emerald-400', bg: 'bg-emerald-500/15' },
  cancelled: { icon: XCircle, color: 'text-red-400', bg: 'bg-red-500/15' },
};

export default function Thumbnails() {
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchExperiments = useCallback(async () => {
    try {
      const res = await api.get('/thumbnails/experiments');
      setExperiments(res.data.experiments || []);
    } catch { /* empty */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchExperiments(); }, [fetchExperiments]);

  const rotateVariant = async (id) => {
    try {
      await api.post(`/thumbnails/experiments/${id}/rotate`);
      fetchExperiments();
    } catch { /* empty */ }
  };

  const conclude = async (id) => {
    try {
      await api.post(`/thumbnails/experiments/${id}/conclude`, { force: false });
      fetchExperiments();
    } catch { /* empty */ }
  };

  const cancel = async (id) => {
    try {
      await api.post(`/thumbnails/experiments/${id}/cancel`);
      fetchExperiments();
    } catch { /* empty */ }
  };

  if (loading) return <div className="max-w-5xl mx-auto"><SkeletonStatCards /></div>;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <PageHeader title="Thumbnail A/B Testing" subtitle="Test thumbnail variants to maximize click-through rate" />

      {experiments.length === 0 ? (
        <EmptyState icon={Image} title="No experiments yet" description="Thumbnail experiments are automatically created when you generate videos with multiple thumbnail concepts." />
      ) : (
        <StaggerContainer className="space-y-4">
          {experiments.map((exp) => {
            const style = STATUS_STYLES[exp.status] || STATUS_STYLES.running;
            const StatusIcon = style.icon;
            return (
              <StaggerItem key={exp.id}>
                <div className="card p-5">
                  {/* Header */}
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${style.bg}`}>
                        <StatusIcon size={16} className={style.color} />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-white text-[14px] font-medium">Experiment</span>
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${style.bg} ${style.color}`}>{exp.status}</span>
                        </div>
                        <p className="text-surface-600 text-[12px] mt-0.5">
                          Started {new Date(exp.started_at).toLocaleDateString()} · {exp.rotation_count} rotations
                        </p>
                      </div>
                    </div>
                    {exp.status === 'running' && (
                      <div className="flex gap-2">
                        <button onClick={() => rotateVariant(exp.id)} title="Rotate variant"
                          className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-blue-400 transition-colors">
                          <RotateCcw size={16} />
                        </button>
                        <button onClick={() => conclude(exp.id)} title="Conclude experiment"
                          className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-emerald-400 transition-colors">
                          <CheckCircle2 size={16} />
                        </button>
                        <button onClick={() => cancel(exp.id)} title="Cancel experiment"
                          className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-red-400 transition-colors">
                          <XCircle size={16} />
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Variants */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {(exp.variants || []).map((v) => (
                      <div key={v.id} className={`rounded-xl p-4 border ${v.id === exp.winner_variant_id ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-white/[0.04] bg-white/[0.02]'}`}>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-white text-[13px] font-medium">{v.concept}</span>
                          {v.id === exp.winner_variant_id && <Trophy size={14} className="text-emerald-400" />}
                        </div>
                        <div className="flex items-center gap-4">
                          <div>
                            <p className="text-surface-600 text-[10px]">Impressions</p>
                            <p className="text-white text-[14px] font-semibold">{v.impressions.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="text-surface-600 text-[10px]">Clicks</p>
                            <p className="text-white text-[14px] font-semibold">{v.clicks.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="text-surface-600 text-[10px]">CTR</p>
                            <p className="text-white text-[14px] font-semibold">{v.ctr_pct || '—'}%</p>
                          </div>
                        </div>
                        {v.is_active && exp.status === 'running' && (
                          <span className="inline-block mt-2 px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400 text-[10px] font-medium">ACTIVE</span>
                        )}
                      </div>
                    ))}
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
