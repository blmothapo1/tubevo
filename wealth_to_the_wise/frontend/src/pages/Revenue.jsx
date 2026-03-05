import { useState, useEffect, useCallback } from 'react';
import api from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonStatCards } from '../components/Skeleton';
import {
  DollarSign, TrendingUp, BarChart3, Plus, X, CreditCard, Percent, Film,
} from 'lucide-react';

function formatCents(cents) {
  return `$${(cents / 100).toFixed(2)}`;
}

const SOURCE_COLORS = {
  adsense: 'bg-blue-500/15 text-blue-400',
  affiliate: 'bg-purple-500/15 text-purple-400',
  stripe: 'bg-emerald-500/15 text-emerald-400',
  manual: 'bg-amber-500/15 text-amber-400',
};

export default function Revenue() {
  const [summary, setSummary] = useState(null);
  const [daily, setDaily] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('overview');
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ source: 'manual', amount_cents: '', event_date: '' });
  const [adding, setAdding] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [sumRes, dailyRes, evRes] = await Promise.all([
        api.get('/revenue/summary'),
        api.get('/revenue/daily'),
        api.get('/revenue/events'),
      ]);
      setSummary(sumRes.data);
      setDaily(dailyRes.data.daily || []);
      setEvents(evRes.data.events || []);
    } catch { /* empty */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const addEvent = async () => {
    if (!form.amount_cents || !form.event_date) return;
    setAdding(true);
    try {
      await api.post('/revenue/events', {
        source: form.source,
        amount_cents: parseInt(form.amount_cents),
        event_date: form.event_date,
      });
      setForm({ source: 'manual', amount_cents: '', event_date: '' });
      setShowAdd(false);
      fetchData();
    } catch { /* empty */ } finally {
      setAdding(false);
    }
  };

  if (loading) return <div className="max-w-5xl mx-auto"><SkeletonStatCards /></div>;

  const statCards = summary ? [
    { label: 'Total Revenue', value: formatCents(summary.total_cents), icon: DollarSign, gradient: 'from-emerald-500/15 to-emerald-500/5', iconColor: 'text-emerald-400' },
    { label: 'Daily Average', value: formatCents(summary.daily_average_cents), icon: TrendingUp, gradient: 'from-blue-500/15 to-blue-500/5', iconColor: 'text-blue-400' },
    { label: 'Days Tracked', value: summary.days_covered, icon: BarChart3, gradient: 'from-purple-500/15 to-purple-500/5', iconColor: 'text-purple-400' },
    { label: 'AdSense', value: formatCents(summary.adsense_cents), icon: Percent, gradient: 'from-amber-500/15 to-amber-500/5', iconColor: 'text-amber-400' },
  ] : [];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <FadeIn>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white">Revenue</h1>
            <p className="text-surface-600 text-[13px] mt-1">Track income from all sources</p>
          </div>
          <button onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-[13px] font-medium transition-colors">
            <Plus size={16} /> Log Revenue
          </button>
        </div>
      </FadeIn>

      {/* Stat cards */}
      {summary && (
        <FadeIn delay={0.05}>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {statCards.map(({ label, value, icon: Icon, gradient, iconColor }) => (
              <div key={label} className={`glass rounded-2xl p-4 bg-gradient-to-br ${gradient}`}>
                <div className="flex items-center gap-2 mb-2">
                  <Icon size={16} className={iconColor} />
                  <span className="text-surface-600 text-[11px]">{label}</span>
                </div>
                <p className="text-white font-semibold text-[18px]">{value}</p>
              </div>
            ))}
          </div>
        </FadeIn>
      )}

      {/* Source breakdown */}
      {summary && (
        <FadeIn delay={0.1}>
          <div className="glass rounded-2xl p-5">
            <h3 className="text-white font-medium text-[14px] mb-3">Revenue by Source</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'AdSense', value: summary.adsense_cents, color: SOURCE_COLORS.adsense },
                { label: 'Affiliate', value: summary.affiliate_cents, color: SOURCE_COLORS.affiliate },
                { label: 'Stripe', value: summary.stripe_cents, color: SOURCE_COLORS.stripe },
                { label: 'Manual', value: summary.manual_cents, color: SOURCE_COLORS.manual },
              ].map((s) => (
                <div key={s.label} className="bg-white/[0.02] rounded-xl p-3">
                  <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${s.color}`}>{s.label}</span>
                  <p className="text-white font-semibold text-[16px] mt-2">{formatCents(s.value)}</p>
                </div>
              ))}
            </div>
          </div>
        </FadeIn>
      )}

      {/* Tabs */}
      <div className="flex gap-1 p-1 glass rounded-xl w-fit">
        {['overview', 'events'].map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-colors ${tab === t ? 'bg-brand-500/20 text-brand-400' : 'text-surface-600 hover:text-surface-900'}`}>
            {t === 'overview' ? 'Daily Breakdown' : 'Events'}
          </button>
        ))}
      </div>

      {/* Daily breakdown */}
      {tab === 'overview' && (
        daily.length === 0 ? (
          <FadeIn><div className="glass rounded-2xl p-12 text-center">
            <BarChart3 size={40} className="mx-auto text-surface-600 mb-4" />
            <p className="text-white font-medium mb-1">No revenue data yet</p>
            <p className="text-surface-600 text-[13px]">Log revenue events to see daily breakdowns.</p>
          </div></FadeIn>
        ) : (
          <StaggerContainer className="space-y-2">
            {daily.map((d) => (
              <StaggerItem key={d.id}>
                <div className="glass rounded-xl p-4 flex items-center justify-between">
                  <div>
                    <p className="text-white text-[13px] font-medium">{d.agg_date}</p>
                    <p className="text-surface-600 text-[11px] mt-0.5">{d.video_count} videos</p>
                  </div>
                  <div className="text-right">
                    <p className="text-white font-semibold text-[15px]">{formatCents(d.total_cents)}</p>
                    <div className="flex gap-2 mt-0.5">
                      {d.adsense_cents > 0 && <span className="text-[10px] text-blue-400">AdS: {formatCents(d.adsense_cents)}</span>}
                      {d.affiliate_cents > 0 && <span className="text-[10px] text-purple-400">Aff: {formatCents(d.affiliate_cents)}</span>}
                      {d.stripe_cents > 0 && <span className="text-[10px] text-emerald-400">Str: {formatCents(d.stripe_cents)}</span>}
                    </div>
                  </div>
                </div>
              </StaggerItem>
            ))}
          </StaggerContainer>
        )
      )}

      {/* Events */}
      {tab === 'events' && (
        events.length === 0 ? (
          <FadeIn><div className="glass rounded-2xl p-12 text-center">
            <CreditCard size={40} className="mx-auto text-surface-600 mb-4" />
            <p className="text-white font-medium mb-1">No events recorded</p>
            <p className="text-surface-600 text-[13px]">Log your first revenue event to get started.</p>
          </div></FadeIn>
        ) : (
          <StaggerContainer className="space-y-2">
            {events.map((e) => (
              <StaggerItem key={e.id}>
                <div className="glass rounded-xl p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${SOURCE_COLORS[e.source] || 'bg-white/5 text-surface-600'}`}>{e.source}</span>
                    <span className="text-surface-600 text-[12px]">{e.event_date}</span>
                  </div>
                  <p className="text-white font-semibold text-[14px]">{formatCents(e.amount_cents)}</p>
                </div>
              </StaggerItem>
            ))}
          </StaggerContainer>
        )
      )}

      {/* Add event modal */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowAdd(false)}>
          <div className="glass rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-semibold">Log Revenue Event</h2>
              <button onClick={() => setShowAdd(false)} className="text-surface-600 hover:text-white"><X size={18} /></button>
            </div>
            <div className="space-y-3">
              <select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}
                className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.06] text-white text-[13px] focus:outline-none focus:ring-1 focus:ring-brand-500/50">
                <option value="manual">Manual</option>
                <option value="adsense">AdSense</option>
                <option value="affiliate">Affiliate</option>
                <option value="stripe">Stripe</option>
              </select>
              <input type="number" placeholder="Amount (cents)" value={form.amount_cents}
                onChange={(e) => setForm({ ...form, amount_cents: e.target.value })}
                className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.06] text-white text-[13px] placeholder:text-surface-600 focus:outline-none focus:ring-1 focus:ring-brand-500/50" />
              <input type="date" value={form.event_date}
                onChange={(e) => setForm({ ...form, event_date: e.target.value })}
                className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.06] text-white text-[13px] focus:outline-none focus:ring-1 focus:ring-brand-500/50" />
            </div>
            <div className="flex gap-3 mt-4">
              <button onClick={() => setShowAdd(false)} className="flex-1 py-2.5 rounded-xl border border-white/[0.06] text-surface-700 text-[13px] font-medium hover:bg-white/[0.02]">Cancel</button>
              <button onClick={addEvent} disabled={adding || !form.amount_cents || !form.event_date}
                className="flex-1 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-[13px] font-medium disabled:opacity-50 transition-colors">
                {adding ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
