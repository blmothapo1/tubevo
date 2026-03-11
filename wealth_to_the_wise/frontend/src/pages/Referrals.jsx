import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import api from '../lib/api';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import { FadeIn } from '../components/Motion';
import {
  Gift, Users, DollarSign, TrendingUp, Copy, Check,
  ExternalLink, Clock, ArrowUpRight, UserPlus,
  RefreshCw, Sparkles, ChevronDown, Share2,
} from 'lucide-react';

/* ── Animated number ── */
function AnimNum({ value, prefix = '', suffix = '' }) {
  return (
    <motion.span
      key={value}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      {prefix}{typeof value === 'number' ? value.toLocaleString() : value}{suffix}
    </motion.span>
  );
}

/* ── Stat card ── */
function StatCard({ icon: Icon, iconColor, gradient, label, value, prefix, suffix, sub, delay = 0 }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay, ease: [0.25, 0.1, 0.25, 1] }}
      className="card p-5 max-sm:p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div className={`w-9 h-9 rounded-[10px] bg-gradient-to-br ${gradient} flex items-center justify-center`}>
          <Icon size={17} className={iconColor} />
        </div>
      </div>
      <p className="text-[24px] sm:text-[28px] font-bold text-white tabular-nums tracking-tight leading-none mb-1">
        <AnimNum value={value} prefix={prefix} suffix={suffix} />
      </p>
      <p className="text-[13px] font-medium text-surface-800">{label}</p>
      {sub && <p className="text-[11px] text-surface-500 mt-0.5">{sub}</p>}
    </motion.div>
  );
}

/* ── Share link card ── */
function ShareCard({ code, shareUrl }) {
  const [copied, setCopied] = useState(false);

  const copyLink = () => {
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const copyCode = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.1 }}
      className="card p-6 border-l-2 border-l-brand-500/50"
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-[12px] bg-gradient-to-br from-brand-500/20 to-brand-600/10 flex items-center justify-center">
          <Share2 size={18} className="text-brand-400" />
        </div>
        <div>
          <h3 className="text-[15px] font-semibold text-white">Your Referral Link</h3>
          <p className="text-[12px] text-surface-500">Share this link to earn commissions</p>
        </div>
      </div>

      {/* Link field */}
      <div className="flex items-center gap-2 mb-3">
        <div className="flex-1 bg-white/[0.03] border border-[var(--border-subtle)] rounded-[10px] px-3.5 py-2.5 text-[13px] text-surface-800 font-mono truncate select-all">
          {shareUrl}
        </div>
        <button
          onClick={copyLink}
          className={`shrink-0 flex items-center gap-1.5 px-3.5 py-2.5 rounded-[10px] text-[12px] font-semibold transition-all
            ${copied
              ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
              : 'bg-brand-500 hover:bg-brand-600 text-white'
            }`}
        >
          {copied ? <><Check size={14} /> Copied</> : <><Copy size={14} /> Copy</>}
        </button>
      </div>

      {/* Code display */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] text-surface-500">Your code:</span>
        <button
          onClick={copyCode}
          className="text-[13px] font-semibold text-brand-400 hover:text-brand-300 transition-colors font-mono tracking-wider"
        >
          {code}
        </button>
      </div>
    </motion.div>
  );
}

/* ── How it works ── */
function HowItWorks({ commissionPct, commissionMonths }) {
  const steps = [
    { icon: Share2, title: 'Share your link', desc: 'Send your unique referral link to friends, followers, or clients' },
    { icon: UserPlus, title: 'They sign up', desc: 'When someone signs up through your link, they\'re tracked as your referral' },
    { icon: DollarSign, title: `Earn ${commissionPct}%`, desc: `You earn ${commissionPct}% recurring commission for ${commissionMonths} months on their subscription` },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.2 }}
      className="card p-6"
    >
      <h3 className="text-[15px] font-semibold text-white mb-4 flex items-center gap-2">
        <Sparkles size={16} className="text-brand-400" /> How It Works
      </h3>
      <div className="grid sm:grid-cols-3 gap-4">
        {steps.map((step, i) => (
          <div key={i} className="flex gap-3 p-3 rounded-[10px] bg-white/[0.02]">
            <div className="w-8 h-8 rounded-[8px] bg-brand-500/10 flex items-center justify-center shrink-0">
              <step.icon size={15} className="text-brand-400" />
            </div>
            <div>
              <p className="text-[13px] font-semibold text-white mb-0.5">{step.title}</p>
              <p className="text-[11px] text-surface-500 leading-relaxed">{step.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

/* ── Referred users list ── */
function ReferredList({ referred }) {
  if (!referred?.length) return null;

  const statusColors = {
    signup: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    converted: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    churned: 'bg-red-500/10 text-red-400 border-red-500/20',
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.3 }}
      className="card overflow-hidden"
    >
      <div className="px-5 py-4 border-b border-[var(--border-subtle)]">
        <h3 className="text-[15px] font-semibold text-white flex items-center gap-2">
          <Users size={16} className="text-brand-400" />
          Referred Users ({referred.length})
        </h3>
      </div>
      <div className="divide-y divide-[var(--border-subtle)]">
        {referred.map((r, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 * i, duration: 0.2 }}
            className="flex items-center gap-3 px-5 py-3 hover:bg-white/[0.02] transition-colors"
          >
            <div className="w-8 h-8 rounded-[8px] bg-surface-200 flex items-center justify-center shrink-0">
              <span className="text-[11px] font-bold text-surface-700">
                {(r.full_name || r.email_masked)[0].toUpperCase()}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-medium text-surface-900 truncate">
                {r.full_name || r.email_masked}
              </p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[11px] text-surface-500">{r.email_masked}</span>
                <span className="text-[10px] text-surface-500 capitalize">· {r.plan} plan</span>
              </div>
            </div>
            <div className="text-right shrink-0">
              {r.earned_cents > 0 && (
                <p className="text-[13px] font-semibold text-emerald-400 tabular-nums">
                  ${(r.earned_cents / 100).toFixed(2)}
                </p>
              )}
            </div>
            <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full border shrink-0 ${statusColors[r.status] || statusColors.signup}`}>
              {r.status}
            </span>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

/* ── Payouts list ── */
function PayoutsList({ payouts }) {
  if (!payouts?.length) return null;

  const statusColors = {
    pending: 'bg-amber-500/10 text-amber-400',
    paid: 'bg-emerald-500/10 text-emerald-400',
    failed: 'bg-red-500/10 text-red-400',
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.4 }}
      className="card overflow-hidden"
    >
      <div className="px-5 py-4 border-b border-[var(--border-subtle)]">
        <h3 className="text-[15px] font-semibold text-white flex items-center gap-2">
          <DollarSign size={16} className="text-emerald-400" />
          Commission History
        </h3>
      </div>
      <div className="divide-y divide-[var(--border-subtle)]">
        {payouts.map((p, i) => (
          <div key={p.id} className="flex items-center gap-3 px-5 py-3 hover:bg-white/[0.02] transition-colors">
            <div className="w-8 h-8 rounded-[8px] bg-emerald-500/10 flex items-center justify-center shrink-0">
              <DollarSign size={14} className="text-emerald-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-medium text-surface-900">
                ${(p.amount_cents / 100).toFixed(2)} commission
              </p>
              <p className="text-[11px] text-surface-500">
                {p.referred_email_masked} · {p.trigger} · {new Date(p.created_at).toLocaleDateString()}
              </p>
            </div>
            <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full shrink-0 ${statusColors[p.status] || ''}`}>
              {p.status}
            </span>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   MAIN PAGE
   ══════════════════════════════════════════════════════════════════════ */
export default function Referrals() {
  const [dashboard, setDashboard] = useState(null);
  const [referred, setReferred] = useState([]);
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [dashRes, refRes, payRes] = await Promise.all([
        api.get('/api/referrals/dashboard'),
        api.get('/api/referrals/referred'),
        api.get('/api/referrals/payouts'),
      ]);
      setDashboard(dashRes.data);
      setReferred(refRes.data);
      setPayouts(payRes.data);
    } catch (err) {
      console.error('Failed to fetch referral data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto">
        <PageHeader title="Referrals" subtitle="Earn commissions by referring others" />
        <div className="flex items-center justify-center h-40">
          <RefreshCw size={20} className="text-surface-500 animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <PageHeader
        title="Referrals"
        subtitle="Earn commissions by referring others to Tubevo"
      />

      {/* Share card */}
      {dashboard && (
        <ShareCard code={dashboard.referral_code} shareUrl={dashboard.share_url} />
      )}

      {/* Stats grid */}
      {dashboard && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            icon={Users}
            iconColor="text-brand-400"
            gradient="from-brand-500/20 to-brand-600/10"
            label="Total Referred"
            value={dashboard.total_referred}
            sub="Users who signed up"
            delay={0}
          />
          <StatCard
            icon={TrendingUp}
            iconColor="text-emerald-400"
            gradient="from-emerald-500/20 to-emerald-600/10"
            label="Converted"
            value={dashboard.total_converted}
            sub="Upgraded to paid"
            delay={0.05}
          />
          <StatCard
            icon={DollarSign}
            iconColor="text-emerald-400"
            gradient="from-emerald-500/20 to-emerald-600/10"
            label="Total Earned"
            value={(dashboard.total_earned_cents / 100).toFixed(2)}
            prefix="$"
            sub="Paid commissions"
            delay={0.1}
          />
          <StatCard
            icon={Clock}
            iconColor="text-amber-400"
            gradient="from-amber-500/20 to-amber-600/10"
            label="Pending"
            value={(dashboard.total_pending_cents / 100).toFixed(2)}
            prefix="$"
            sub="Awaiting payout"
            delay={0.15}
          />
        </div>
      )}

      {/* How it works */}
      {dashboard && (
        <HowItWorks
          commissionPct={dashboard.commission_pct}
          commissionMonths={dashboard.commission_months}
        />
      )}

      {/* Referred users */}
      <ReferredList referred={referred} />

      {/* Payouts */}
      <PayoutsList payouts={payouts} />

      {/* Empty state when no referrals yet */}
      {referred.length === 0 && !loading && (
        <FadeIn delay={0.2}>
          <EmptyState
            icon={Gift}
            title="No referrals yet"
            subtitle="Share your referral link above to start earning commissions. You'll earn 20% of every subscription payment for 12 months."
          />
        </FadeIn>
      )}
    </div>
  );
}
