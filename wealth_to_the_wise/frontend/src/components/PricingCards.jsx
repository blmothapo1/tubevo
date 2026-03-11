import { useState } from 'react';
import { motion } from 'framer-motion';
import { Check, Sparkles, Zap, Rocket, Crown, Loader2 } from 'lucide-react';
import api from '../lib/api';

/* ─────────────────────────────────────────────────────────────────────
   PLAN DATA — single source of truth for pricing UI
   ───────────────────────────────────────────────────────────────────── */
const PLANS = [
  {
    key: 'starter',
    name: 'Starter',
    price: 29,
    icon: Zap,
    accent: 'brand',
    description: 'Perfect for getting started with automated video creation.',
    features: [
      '10 videos / month',
      '1080p HD @ 30fps',
      'GPT-4o scripts',
      '10 scenes per video',
      '3 team seats · 1 team',
      'All video styles',
      'Auto-scheduling',
      'YouTube upload',
      'Email support',
    ],
  },
  {
    key: 'pro',
    name: 'Pro',
    price: 79,
    icon: Rocket,
    accent: 'violet',
    popular: true,
    description: 'For serious creators who want to scale their channel.',
    features: [
      '50 videos / month',
      '1080p HD @ 30fps · Best quality',
      'GPT-4o scripts (longer, deeper)',
      '14 scenes per video',
      '10 team seats · 3 teams',
      'Everything in Starter',
      'Multi-format export',
      'Trend Radar',
      'Performance Insights',
      'Voice clones',
      'Priority support',
    ],
  },
  {
    key: 'agency',
    name: 'Agency',
    price: 199,
    icon: Crown,
    accent: 'amber',
    description: 'Unlimited power for agencies and multi-channel operations.',
    features: [
      'Unlimited videos',
      '1080p HD @ 30fps · Studio quality',
      'GPT-4o scripts (max depth)',
      '18 scenes per video',
      '25 team seats · 10 teams',
      'Everything in Pro',
      'Bulk generation',
      'Custom export formats',
      'Niche intelligence',
      'Dedicated support',
    ],
  },
];

const ACCENT_MAP = {
  brand: {
    gradient: 'from-brand-500 to-brand-600',
    bg: 'bg-brand-500/10',
    text: 'text-brand-400',
    border: 'border-brand-500/20',
    btn: 'bg-brand-500 hover:bg-brand-600',
    ring: 'ring-brand-500/30',
    badge: 'bg-brand-500/15 text-brand-400 border-brand-500/25',
    popularBorder: 'border-brand-500/30 ring-1 ring-brand-500/30 shadow-lg shadow-brand-500/5',
    hoverBorder: 'hover:border-brand-500/30',
  },
  violet: {
    gradient: 'from-violet-500 to-violet-600',
    bg: 'bg-violet-500/10',
    text: 'text-violet-400',
    border: 'border-violet-500/20',
    btn: 'bg-violet-500 hover:bg-violet-600',
    ring: 'ring-violet-500/30',
    badge: 'bg-violet-500/15 text-violet-400 border-violet-500/25',
    popularBorder: 'border-violet-500/30 ring-1 ring-violet-500/30 shadow-lg shadow-violet-500/5',
    hoverBorder: 'hover:border-violet-500/30',
  },
  amber: {
    gradient: 'from-amber-500 to-amber-600',
    bg: 'bg-amber-500/10',
    text: 'text-amber-400',
    border: 'border-amber-500/20',
    btn: 'bg-amber-500 hover:bg-amber-600',
    ring: 'ring-amber-500/30',
    badge: 'bg-amber-500/15 text-amber-400 border-amber-500/25',
    popularBorder: 'border-amber-500/30 ring-1 ring-amber-500/30 shadow-lg shadow-amber-500/5',
    hoverBorder: 'hover:border-amber-500/30',
  },
};

/* ─────────────────────────────────────────────────────────────────────
   PRICING CARD (single plan)
   ───────────────────────────────────────────────────────────────────── */
function PricingCard({ plan, currentPlan, authenticated, delay = 0 }) {
  const [loading, setLoading] = useState(false);
  const a = ACCENT_MAP[plan.accent];
  const Icon = plan.icon;
  const isCurrent = currentPlan === plan.key;

  async function handleUpgrade() {
    if (!authenticated) {
      window.location.href = '/signup';
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post('/billing/create-checkout-session', { plan: plan.key });
      window.location.href = data.checkout_url;
    } catch (err) {
      const detail = err.response?.data?.detail || 'Something went wrong';
      alert(detail);  // fallback — this rarely fires
    } finally {
      setLoading(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.35, ease: [0.25, 0.1, 0.25, 1] }}
      className={`relative flex flex-col rounded-[16px] border p-6 transition-all duration-200
        ${plan.popular ? a.popularBorder : 'border-[var(--border-subtle)]'}
        bg-[var(--card-bg)] ${a.hoverBorder}`}
    >
      {/* Popular badge */}
      {plan.popular && (
        <div className={`absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border ${a.badge}`}>
          <span className="flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> Most Popular
          </span>
        </div>
      )}

      {/* Icon + name */}
      <div className="flex items-center gap-3 mb-4">
        <div className={`w-9 h-9 rounded-[10px] ${a.bg} flex items-center justify-center`}>
          <Icon className={`w-[18px] h-[18px] ${a.text}`} />
        </div>
        <div>
          <h3 className="text-[15px] font-semibold text-white">{plan.name}</h3>
        </div>
      </div>

      {/* Price */}
      <div className="mb-3">
        <div className="flex items-baseline gap-1">
          <span className="text-[32px] font-bold text-white tracking-tight">${plan.price}</span>
          <span className="text-[13px] text-surface-500 font-medium">/mo</span>
        </div>
      </div>

      {/* Description */}
      <p className="text-[12px] text-surface-500 leading-relaxed mb-5">
        {plan.description}
      </p>

      {/* CTA */}
      <button
        onClick={handleUpgrade}
        disabled={loading || isCurrent}
        className={`w-full py-2.5 rounded-[10px] text-[13px] font-semibold text-white transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 ${
          isCurrent
            ? 'bg-white/[0.06] border border-[var(--border-subtle)] !text-surface-500'
            : a.btn
        }`}
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : isCurrent ? (
          'Current Plan'
        ) : (
          <>Get {plan.name}</>
        )}
      </button>

      {/* Features */}
      <ul className="mt-5 space-y-2.5">
        {plan.features.map((f) => (
          <li key={f} className="flex items-start gap-2.5 text-[12px]">
            <Check className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${a.text}`} />
            <span className="text-surface-600">{f}</span>
          </li>
        ))}
      </ul>
    </motion.div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   PRICING CARDS GRID (exported)
   ───────────────────────────────────────────────────────────────────── */

/**
 * @param {Object} props
 * @param {string} [props.currentPlan]  — The user's current plan key (e.g. "free", "starter")
 * @param {boolean} [props.authenticated] — Whether user is logged in (for CTA behavior)
 */
export default function PricingCards({ currentPlan = 'free', authenticated = false }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-4xl mx-auto">
      {PLANS.map((plan, i) => (
        <PricingCard
          key={plan.key}
          plan={plan}
          currentPlan={currentPlan}
          authenticated={authenticated}
          delay={i * 0.08}
        />
      ))}
    </div>
  );
}
