import { useState, useEffect, useCallback } from 'react';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonStatCards } from '../components/Skeleton';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import {
  Search, TrendingUp, BarChart3, Zap, Target, ArrowUpRight, ArrowDownRight, Minus,
} from 'lucide-react';

function ScoreBadge({ label, value, max = 100 }) {
  const pct = Math.round((value / max) * 100);
  const color = pct >= 70 ? 'text-emerald-400 bg-emerald-500/15' : pct >= 40 ? 'text-amber-400 bg-amber-500/15' : 'text-red-400 bg-red-500/15';
  return (
    <div className={`px-3 py-1.5 rounded-lg ${color} text-[12px] font-medium`}>
      {label}: {value}
    </div>
  );
}

export default function NicheIntel() {
  const [snapshots, setSnapshots] = useState([]);
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [niche, setNiche] = useState('');
  const [tab, setTab] = useState('snapshots');

  const fetchData = useCallback(async () => {
    try {
      const [snapRes, topicRes] = await Promise.all([
        api.get('/niche/snapshots'),
        api.get('/niche/topics'),
      ]);
      setSnapshots(snapRes.data.snapshots || []);
      setTopics(topicRes.data.topics || []);
    } catch { /* empty */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const runScan = async () => {
    if (!niche.trim()) return;
    setScanning(true);
    try {
      await api.post('/niche/scan', { niche: niche.trim() });
      setNiche('');
      fetchData();
    } catch { /* empty */ } finally {
      setScanning(false);
    }
  };

  if (loading) return <div className="max-w-5xl mx-auto"><SkeletonStatCards /></div>;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <PageHeader title="Niche Intelligence" subtitle="Analyze niches and discover high-demand topics" />

      {/* Scan input */}
      <FadeIn delay={0.05}>
        <div className="card p-5">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-surface-600" />
              <input
                value={niche}
                onChange={(e) => setNiche(e.target.value)}
                placeholder="Enter a niche to analyze (e.g., personal finance, crypto trading)"
                className="input-field !pl-11"
                onKeyDown={(e) => e.key === 'Enter' && runScan()}
              />
            </div>
            <button onClick={runScan} disabled={scanning || !niche.trim()}
              className="btn-primary flex items-center gap-2 text-[13px]">
              <Zap size={16} /> {scanning ? 'Scanning…' : 'Scan'}
            </button>
          </div>
        </div>
      </FadeIn>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-surface-100 rounded-[10px] w-fit">
        {['snapshots', 'topics'].map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-colors ${tab === t ? 'bg-brand-500/20 text-brand-400' : 'text-surface-600 hover:text-surface-900'}`}>
            {t === 'snapshots' ? 'Snapshots' : 'Topic Ideas'}
          </button>
        ))}
      </div>

      {/* Snapshots tab */}
      {tab === 'snapshots' && (
        snapshots.length === 0 ? (
          <EmptyState icon={BarChart3} title="No niche scans yet" description="Run your first scan above to analyze a niche." />
        ) : (
          <StaggerContainer className="space-y-3">
            {snapshots.map((s) => (
              <StaggerItem key={s.id}>
                <div className="card p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="text-white font-medium text-[14px]">{s.niche}</h3>
                      <p className="text-surface-600 text-[12px] mt-0.5">{s.snapshot_date}</p>
                    </div>
                    <div className="flex gap-2">
                      <ScoreBadge label="Trend" value={s.trending_score} />
                      <ScoreBadge label="Saturation" value={s.saturation_score} />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
                    <div className="bg-white/[0.02] rounded-xl p-3">
                      <p className="text-surface-600 text-[11px]">Search Volume</p>
                      <p className="text-white font-semibold text-[16px] mt-1">{s.search_volume_est?.toLocaleString()}</p>
                    </div>
                    <div className="bg-white/[0.02] rounded-xl p-3">
                      <p className="text-surface-600 text-[11px]">Competitors</p>
                      <p className="text-white font-semibold text-[16px] mt-1">{s.competitor_count}</p>
                    </div>
                    <div className="bg-white/[0.02] rounded-xl p-3">
                      <p className="text-surface-600 text-[11px]">Trending Score</p>
                      <p className="text-white font-semibold text-[16px] mt-1">{s.trending_score}/100</p>
                    </div>
                    <div className="bg-white/[0.02] rounded-xl p-3">
                      <p className="text-surface-600 text-[11px]">Saturation</p>
                      <p className="text-white font-semibold text-[16px] mt-1">{s.saturation_score}/100</p>
                    </div>
                  </div>
                  {s.topics?.length > 0 && (
                    <div className="mt-4 space-y-2">
                      <p className="text-surface-600 text-[12px] font-medium">Topics ({s.topics.length})</p>
                      <div className="flex flex-wrap gap-2">
                        {s.topics.slice(0, 8).map((t) => (
                          <span key={t.id} className="px-3 py-1 rounded-lg bg-white/[0.04] text-surface-700 text-[12px]">
                            {t.topic}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </StaggerItem>
            ))}
          </StaggerContainer>
        )
      )}

      {/* Topics tab */}
      {tab === 'topics' && (
        topics.length === 0 ? (
          <EmptyState icon={Target} title="No topics discovered" description="Run niche scans to discover topic ideas." />
        ) : (
          <StaggerContainer className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {topics.map((t) => (
              <StaggerItem key={t.id}>
                <div className="card p-4">
                  <p className="text-white text-[13px] font-medium">{t.topic}</p>
                  <div className="flex items-center gap-3 mt-2">
                    <span className="text-surface-600 text-[11px]">Demand: {t.estimated_demand}</span>
                    <span className={`text-[11px] px-2 py-0.5 rounded-full ${t.competition_level === 'low' ? 'bg-emerald-500/15 text-emerald-400' : t.competition_level === 'medium' ? 'bg-amber-500/15 text-amber-400' : 'bg-red-500/15 text-red-400'}`}>
                      {t.competition_level}
                    </span>
                    <span className="text-surface-600 text-[11px]">{t.source}</span>
                  </div>
                </div>
              </StaggerItem>
            ))}
          </StaggerContainer>
        )
      )}
    </div>
  );
}
