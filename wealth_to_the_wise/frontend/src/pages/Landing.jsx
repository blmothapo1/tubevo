import { Link } from 'react-router-dom';
import {
  Sparkles, Mic, Upload, Target, CalendarClock, Zap, Check, ArrowRight,
} from 'lucide-react';

const features = [
  { icon: Sparkles, title: 'AI Script Generation', desc: 'GPT-4o writes engaging, niche-specific scripts in seconds.', iconColor: 'text-brand-400', iconBg: 'bg-brand-600/10' },
  { icon: Mic, title: 'Voice Cloning', desc: 'ElevenLabs TTS creates natural voiceovers that sound like you.', iconColor: 'text-violet-400', iconBg: 'bg-violet-500/10' },
  { icon: Upload, title: 'Auto-Upload', desc: 'Videos are rendered, optimized, and uploaded to YouTube automatically.', iconColor: 'text-emerald-400', iconBg: 'bg-emerald-500/10' },
  { icon: Target, title: 'Niche Targeting', desc: 'Choose your niche and let the AI generate content that resonates.', iconColor: 'text-amber-400', iconBg: 'bg-amber-500/10' },
  { icon: CalendarClock, title: 'Posting Schedule', desc: 'Set your cadence — daily, every 2 days, or weekly.', iconColor: 'text-cyan-400', iconBg: 'bg-cyan-500/10' },
  { icon: Zap, title: 'Zero Effort', desc: 'From idea to published video with absolutely no manual steps.', iconColor: 'text-rose-400', iconBg: 'bg-rose-500/10' },
];

const tiers = [
  {
    name: 'Starter',
    price: '$29',
    period: '/mo',
    features: [
      '1 YouTube channel connected',
      'Up to 12 videos per month',
      'Basic niche templates',
      'Standard processing',
    ],
    cta: 'Start Starter',
    popular: false,
  },
  {
    name: 'Pro',
    price: '$79',
    period: '/mo',
    features: [
      'Up to 3 YouTube channels connected',
      'Up to 60 videos per month',
      'More niche templates',
      'Faster processing vs Starter',
    ],
    cta: 'Start Pro',
    popular: true,
  },
  {
    name: 'Agency',
    price: '$199',
    period: '/mo',
    features: [
      'Unlimited YouTube channels connected',
      'Unlimited videos (fair-use limits may apply)',
      'Priority processing',
      'Priority support',
    ],
    cta: 'Contact Sales',
    popular: false,
  },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-surface-50">
      {/* Navbar */}
      <nav className="border-b border-surface-300/50 backdrop-blur-sm bg-surface-50/80 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <span className="text-xl font-bold tracking-tight text-white">
            <span className="text-brand-400">Tube</span>vo
          </span>
          <div className="flex items-center gap-4">
            <Link to="/login" className="text-sm text-surface-700 hover:text-surface-900 transition-colors">
              Log in
            </Link>
            <Link
              to="/signup"
              className="text-sm font-medium bg-brand-600 hover:bg-brand-500 text-white px-4 py-2 rounded-lg transition-colors"
            >
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-4xl mx-auto px-4 sm:px-6 pt-16 sm:pt-28 pb-14 sm:pb-20 text-center relative">
        {/* Subtle background glow */}
        <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-brand-600/8 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute top-32 left-1/3 w-[300px] h-[300px] bg-accent-500/5 rounded-full blur-3xl pointer-events-none" />

        <div className="relative">
          <div className="inline-flex items-center gap-2 bg-brand-600/10 border border-brand-600/20 text-brand-300 text-xs font-medium px-3 py-1 rounded-full mb-6">
            <Zap size={12} className="text-accent-400" /> Now in public beta
          </div>
          <h1 className="text-3xl sm:text-5xl md:text-6xl font-bold tracking-tight text-white leading-tight">
            Your YouTube Channel.
            <br />
            <span className="text-gradient">On Autopilot.</span>
          </h1>
          <p className="mt-4 sm:mt-6 text-base sm:text-lg text-surface-700 max-w-2xl mx-auto leading-relaxed">
            Tubevo generates scripts, creates voiceovers, builds videos, and uploads them to your channel — fully automated, powered by AI.
          </p>
          <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              to="/signup"
              className="inline-flex items-center gap-2 gradient-brand hover:opacity-90 text-white font-medium px-6 py-3 rounded-lg transition-all text-sm glow-brand"
            >
              Get Started Free <ArrowRight size={16} />
            </Link>
            <a
              href="#features"
              className="text-sm text-surface-700 hover:text-surface-900 transition-colors"
            >
              See how it works →
            </a>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="max-w-6xl mx-auto px-4 sm:px-6 py-14 sm:py-20">
        <h2 className="text-2xl sm:text-3xl font-bold text-white text-center mb-4">Everything you need</h2>
        <p className="text-surface-700 text-center mb-14 max-w-lg mx-auto">
          From script to published video — every step is automated.
        </p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {features.map(({ icon: Icon, title, desc, iconColor, iconBg }) => (
            <div
              key={title}
              className="bg-surface-100 border border-surface-300 rounded-xl p-6 hover:border-brand-600/30 hover:bg-surface-100/80 transition-all group"
            >
              <div className={`w-10 h-10 rounded-lg ${iconBg} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                <Icon size={20} className={iconColor} />
              </div>
              <h3 className="text-sm font-semibold text-white mb-2">{title}</h3>
              <p className="text-sm text-surface-700 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="max-w-5xl mx-auto px-4 sm:px-6 py-14 sm:py-20">
        <h2 className="text-2xl sm:text-3xl font-bold text-white text-center mb-4">Simple pricing</h2>
        <p className="text-surface-700 text-center mb-10 sm:mb-14">Start free. Scale when you're ready.</p>
        <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-5">
          {tiers.map((tier) => (
            <div
              key={tier.name}
              className={`relative bg-surface-100 border rounded-xl p-6 flex flex-col ${
                tier.popular ? 'border-brand-500 ring-1 ring-brand-500/20' : 'border-surface-300'
              }`}
            >
              {tier.popular && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 gradient-brand text-white text-xs font-medium px-3 py-0.5 rounded-full">
                  Most popular
                </span>
              )}
              <h3 className="text-lg font-semibold text-white">{tier.name}</h3>
              <div className="mt-4 mb-6">
                <span className="text-4xl font-bold text-white">{tier.price}</span>
                <span className="text-surface-600 text-sm">{tier.period}</span>
              </div>
              <ul className="space-y-3 flex-1">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm text-surface-700">
                    <Check size={16} className="text-brand-400 mt-0.5 shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
              <Link
                to="/signup"
                className={`mt-8 text-center text-sm font-medium py-2.5 rounded-lg transition-all ${
                  tier.popular
                    ? 'gradient-brand hover:opacity-90 text-white glow-brand'
                    : 'bg-surface-200 hover:bg-surface-300 text-surface-900'
                }`}
              >
                {tier.cta}
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-surface-300/50 py-10 text-center text-sm text-surface-600">
        © {new Date().getFullYear()} Tubevo. All rights reserved.
      </footer>
    </div>
  );
}
