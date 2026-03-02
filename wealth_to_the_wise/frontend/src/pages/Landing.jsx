import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sparkles, Mic, Upload, Target, CalendarClock, Zap, Check, ArrowRight, Loader2,
} from 'lucide-react';
import api from '../lib/api';

const ease = [0.25, 0.1, 0.25, 1];

const features = [
  { icon: Sparkles, title: 'AI Script Generation', desc: 'GPT-4o writes engaging, niche-specific scripts in seconds.', color: 'from-indigo-500/20 to-indigo-500/5', iconColor: 'text-indigo-400' },
  { icon: Mic, title: 'Voice Cloning', desc: 'ElevenLabs TTS creates natural voiceovers that sound like you.', color: 'from-violet-500/20 to-violet-500/5', iconColor: 'text-violet-400' },
  { icon: Upload, title: 'Auto-Upload', desc: 'Videos are rendered, optimized, and uploaded to YouTube automatically.', color: 'from-emerald-500/20 to-emerald-500/5', iconColor: 'text-emerald-400' },
  { icon: Target, title: 'Niche Targeting', desc: 'Choose your niche and let the AI generate content that resonates.', color: 'from-amber-500/20 to-amber-500/5', iconColor: 'text-amber-400' },
  { icon: CalendarClock, title: 'Posting Schedule', desc: 'Set your cadence — daily, every 2 days, or weekly.', color: 'from-cyan-500/20 to-cyan-500/5', iconColor: 'text-cyan-400' },
  { icon: Zap, title: 'Zero Effort', desc: 'From idea to published video with absolutely no manual steps.', color: 'from-rose-500/20 to-rose-500/5', iconColor: 'text-rose-400' },
];

const tiers = [
  {
    name: 'Starter',
    price: '$29',
    period: '/mo',
    features: ['10 videos/month', 'All voices', 'Email support', 'Stock footage'],
    cta: 'Start with Starter',
    popular: false,
  },
  {
    name: 'Pro',
    price: '$79',
    period: '/mo',
    features: ['50 videos/month', 'Custom branding', 'Priority support', 'Analytics', 'Auto-scheduling'],
    cta: 'Start with Pro',
    popular: true,
  },
  {
    name: 'Agency',
    price: '$199',
    period: '/mo',
    features: ['Unlimited videos', 'Multi-channel', 'API access', 'Dedicated manager', 'White label'],
    cta: 'Start with Agency',
    popular: false,
  },
];

const stagger = {
  visible: { transition: { staggerChildren: 0.06 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease } },
};

export default function Landing() {
  const [waitlistEmail, setWaitlistEmail] = useState('');
  const [waitlistState, setWaitlistState] = useState('idle'); // idle | loading | success
  const [waitlistError, setWaitlistError] = useState('');
  const [waitlistCount, setWaitlistCount] = useState(null);

  useEffect(() => {
    api.get('/api/waitlist/count')
      .then(res => setWaitlistCount(res.data.count))
      .catch(() => {});
  }, []);

  const handleWaitlistSubmit = async (e) => {
    e.preventDefault();
    setWaitlistError('');

    const email = waitlistEmail.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setWaitlistError('Please enter a valid email address.');
      return;
    }

    setWaitlistState('loading');
    try {
      await api.post('/api/waitlist/subscribe', { email });
      localStorage.setItem('tubevo_waitlist_email', email);
      setWaitlistState('success');
      setWaitlistCount(prev => (prev ?? 0) + 1);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setWaitlistError(typeof detail === 'string' ? detail : 'Something went wrong. Please try again.');
      setWaitlistState('idle');
    }
  };

  return (
    <div style={{ width: '100%', minHeight: '100vh', overflow: 'hidden' }} className="bg-surface-50">
      {/* ── Navbar ── */}
      <nav className="glass sticky top-0 z-50" style={{ width: '100%' }}>
        <div className="landing-container h-[64px] flex items-center justify-between">
          <span className="text-[20px] font-semibold text-white" style={{ fontFamily: "'Poppins', sans-serif" }}>Tubevo</span>
          <div className="flex items-center gap-3">
            <Link
              to="/login"
              className="text-[13px] text-surface-700 hover:text-white px-3 py-2 rounded-[8px] transition-colors duration-150 hover:bg-white/[0.04]"
            >
              Log in
            </Link>
            <Link
              to="/signup"
              className="btn-primary text-[13px] !py-2 !px-5 !rounded-[10px]"
            >
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="relative" style={{ width: '100%' }}>
        <div className="landing-container--narrow pt-28 sm:pt-36 md:pt-44 pb-28 md:pb-36 text-center">
          {/* Ambient background glows — more subtle */}
          <div className="absolute top-10 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-gradient-radial from-brand-600/8 via-brand-600/2 to-transparent rounded-full blur-3xl pointer-events-none" />
          <div className="absolute top-40 left-1/4 w-[250px] h-[250px] bg-accent-500/3 rounded-full blur-3xl pointer-events-none" />

          <motion.div
            initial="hidden"
            animate="visible"
            variants={stagger}
            className="relative flex flex-col items-center"
          >
            <motion.div variants={fadeUp} className="inline-flex items-center gap-2 bg-brand-500/6 text-brand-300 text-[10px] font-semibold uppercase tracking-widest px-3 py-1.5 rounded-[6px] mb-12">
              <Zap size={10} className="text-accent-400" /> Public Beta
            </motion.div>

            <motion.h1 variants={fadeUp} className="text-4xl sm:text-[48px] md:text-[56px] font-bold tracking-[-0.03em] text-white leading-[1.15]">
              Your YouTube Channel.
              <br />
              <span className="text-gradient">On Autopilot.</span>
            </motion.h1>

            <motion.p variants={fadeUp} className="mt-6 text-xl sm:text-[24px] md:text-[28px] font-semibold tracking-[-0.02em] text-surface-900 leading-[1.3]">
              Built to create. Designed to perform.
            </motion.p>

            <motion.p variants={fadeUp} className="mt-4 text-base sm:text-[17px] text-surface-700 max-w-xl leading-[1.7] font-normal">
              Tubevo turns your ideas into high-performing, publish-ready videos.
            </motion.p>

            <motion.div variants={fadeUp} className="mt-14 w-full max-w-[480px]">
              <AnimatePresence mode="wait">
                {waitlistState === 'success' ? (
                  <motion.div
                    key="success"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, ease }}
                    className="flex items-center justify-center gap-2.5 px-6 py-4 rounded-[12px]"
                    style={{
                      background: 'rgba(52,211,153,0.08)',
                      border: '1px solid rgba(52,211,153,0.2)',
                    }}
                  >
                    <div className="w-5 h-5 rounded-full bg-emerald-500/20 flex items-center justify-center shrink-0">
                      <Check size={12} className="text-emerald-400" />
                    </div>
                    <span className="text-[14px] text-surface-900 font-medium">
                      You're on the list! We'll notify you at launch.
                    </span>
                  </motion.div>
                ) : (
                  <motion.div key="form" initial={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
                    <form onSubmit={handleWaitlistSubmit} className="flex flex-col sm:flex-row items-stretch gap-4">
                      <input
                        type="email"
                        placeholder="Enter your email"
                        value={waitlistEmail}
                        onChange={(e) => { setWaitlistEmail(e.target.value); setWaitlistError(''); }}
                        className="flex-1 min-w-0 rounded-[10px] px-4 py-3 text-[14px] text-white placeholder:text-surface-600 outline-none transition-all duration-150"
                        style={{
                          background: 'var(--color-surface-well)',
                          border: '1px solid rgba(255,255,255,0.08)',
                        }}
                        onFocus={(e) => { e.target.style.border = '1px solid rgba(99,102,241,0.5)'; e.target.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.12)'; }}
                        onBlur={(e) => { e.target.style.border = '1px solid rgba(255,255,255,0.08)'; e.target.style.boxShadow = 'none'; }}
                      />
                      <button
                        type="submit"
                        disabled={waitlistState === 'loading'}
                        className="btn-primary !rounded-[10px] !px-6 !py-3 !text-[14px] !font-semibold inline-flex items-center justify-center gap-2 shrink-0 disabled:opacity-70"
                      >
                        {waitlistState === 'loading' ? (
                          <Loader2 size={16} className="animate-spin" />
                        ) : null}
                        {waitlistState === 'loading' ? 'Joining…' : 'Join the Waitlist'}
                      </button>
                    </form>
                    {waitlistError && (
                      <motion.p
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="mt-3 text-[12px] text-red-400 text-center"
                      >
                        {waitlistError}
                      </motion.p>
                    )}
                    <p className="mt-5 text-[12px] text-surface-700 text-center">
                      {waitlistCount !== null && waitlistCount > 0
                        ? `Join ${waitlistCount.toLocaleString()} creator${waitlistCount === 1 ? '' : 's'} already on the waitlist`
                        : 'Be the first to know when we launch'}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>

            <motion.div variants={fadeUp} className="mt-8">
              <a
                href="#features"
                className="text-[13px] text-surface-600 hover:text-surface-800 transition-colors duration-150"
              >
                See how it works →
              </a>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ── Features ── */}
      <section id="features" style={{ width: '100%' }}>
        <div className="landing-container py-[96px] md:py-[140px]">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.4, ease }}
            className="flex flex-col items-center text-center mb-20"
          >
            <h2 className="text-2xl sm:text-[32px] font-bold text-white mb-4 tracking-tight">Everything you need</h2>
            <p className="text-surface-700 max-w-lg mx-auto text-[15px] leading-[1.7]">
              From script to published video — every step is automated.
            </p>
          </motion.div>

          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
            variants={stagger}
            className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 sm:gap-8"
          >
            {features.map(({ icon: Icon, title, desc, color, iconColor }) => (
              <motion.div
                key={title}
                variants={fadeUp}
                className="card p-7 cursor-default"
              >
                <div className={`w-10 h-10 rounded-[10px] bg-gradient-to-br ${color} flex items-center justify-center mb-5`}>
                  <Icon size={18} className={iconColor} />
                </div>
                <h3 className="text-[15px] font-semibold text-white mb-3">{title}</h3>
                <p className="text-[13px] text-surface-700 leading-[1.7]">{desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Pricing ── */}
      <section id="pricing" style={{ width: '100%' }}>
        <div className="landing-container--mid py-[96px] md:py-[140px]">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.4, ease }}
            className="flex flex-col items-center text-center mb-20"
          >
            <h2 className="text-2xl sm:text-[32px] font-bold text-white mb-4 tracking-tight">Simple pricing</h2>
            <p className="text-surface-700 text-[15px] leading-[1.7]">Start free. Scale when you're ready.</p>
          </motion.div>

          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
            variants={stagger}
            className="grid sm:grid-cols-2 md:grid-cols-3 gap-6 sm:gap-8"
          >
            {tiers.map((tier) => (
              <motion.div
                key={tier.name}
                variants={fadeUp}
                className={`relative card p-7 flex flex-col ${
                  tier.popular ? 'ring-1 ring-brand-500/30 border-brand-500/20' : ''
                }`}
              >
                {tier.popular && (
                  <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-brand-500 text-white text-[10px] font-semibold uppercase tracking-wider px-3 py-0.5 rounded-[6px]">
                    Most popular
                  </span>
                )}
                <h3 className="text-[16px] font-semibold text-white">{tier.name}</h3>
                <div className="mt-5 mb-7">
                  <span className="text-[32px] font-bold text-white tracking-tight">{tier.price}</span>
                  <span className="text-surface-600 text-[13px] ml-1">{tier.period}</span>
                </div>
                <ul className="space-y-4 flex-1">
                  {tier.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5 text-[13px] text-surface-700">
                      <Check size={14} className="text-brand-400 mt-0.5 shrink-0" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link
                  to="/signup"
                  className={`mt-8 text-center text-[13px] font-semibold py-3 rounded-[10px] transition-all duration-150 block ${
                    tier.popular
                      ? 'btn-primary w-full'
                      : 'btn-secondary w-full'
                  }`}
                >
                  {tier.cta}
                </Link>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer style={{ width: '100%' }}>
        <div className="landing-container py-20 text-center">
          <p className="text-[13px] text-surface-600">© {new Date().getFullYear()} Tubevo. All rights reserved.</p>
          <div className="mt-4 flex items-center justify-center gap-8">
            <Link to="/privacy" className="text-[13px] text-surface-600 hover:text-surface-800 transition-colors duration-150">Privacy Policy</Link>
            <Link to="/terms" className="text-[13px] text-surface-600 hover:text-surface-800 transition-colors duration-150">Terms of Service</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
