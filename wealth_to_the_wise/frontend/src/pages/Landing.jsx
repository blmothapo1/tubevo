import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Sparkles, Mic, Upload, Target, CalendarClock, Zap, Check, ArrowRight,
} from 'lucide-react';
import tubevoLogo from '../assets/tubevo-logo-web.png';

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
    features: ['1 YouTube channel', 'Up to 12 videos/month', 'Basic niche templates', 'Standard processing'],
    cta: 'Start with Starter',
    popular: false,
  },
  {
    name: 'Pro',
    price: '$79',
    period: '/mo',
    features: ['Up to 3 channels', 'Up to 60 videos/month', 'All templates', 'Faster processing'],
    cta: 'Start with Pro',
    popular: true,
  },
  {
    name: 'Agency',
    price: '$199',
    period: '/mo',
    features: ['Unlimited channels', 'Unlimited videos', 'Priority processing', 'Priority support'],
    cta: 'Start with Agency',
    popular: false,
  },
];

const stagger = {
  visible: { transition: { staggerChildren: 0.08 } },
};

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease } },
};

export default function Landing() {
  return (
    <div className="min-h-screen bg-surface-50 overflow-hidden">
      {/* ── Navbar ── */}
      <nav className="border-b border-surface-300/30 glass sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <img src={tubevoLogo} alt="Tubevo" className="h-8" />
          <div className="flex items-center gap-3">
            <Link
              to="/login"
              className="text-sm text-surface-700 hover:text-white px-4 py-2 rounded-xl transition-all duration-200 hover:bg-surface-200/50"
            >
              Log in
            </Link>
            <Link
              to="/signup"
              className="btn-primary text-sm !py-2 !px-5"
            >
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="relative max-w-4xl mx-auto px-6 pt-20 sm:pt-32 pb-20 text-center">
        {/* Ambient background glows */}
        <div className="absolute top-10 left-1/2 -translate-x-1/2 w-[700px] h-[500px] bg-gradient-radial from-brand-600/10 via-brand-600/3 to-transparent rounded-full blur-3xl pointer-events-none" />
        <div className="absolute top-40 left-1/4 w-[300px] h-[300px] bg-accent-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute top-20 right-1/4 w-[250px] h-[250px] bg-violet-500/5 rounded-full blur-3xl pointer-events-none" />

        <motion.div
          initial="hidden"
          animate="visible"
          variants={stagger}
          className="relative"
        >
          <motion.div variants={fadeUp} className="inline-flex items-center gap-2 bg-brand-600/8 border border-brand-500/15 text-brand-300 text-xs font-medium px-4 py-1.5 rounded-full mb-8">
            <Zap size={12} className="text-accent-400" /> Now in public beta
          </motion.div>

          <motion.h1 variants={fadeUp} className="text-4xl sm:text-5xl md:text-7xl font-bold tracking-tight text-white leading-[1.1]">
            Your YouTube Channel.
            <br />
            <span className="text-gradient">On Autopilot.</span>
          </motion.h1>

          <motion.p variants={fadeUp} className="mt-6 sm:mt-8 text-base sm:text-lg text-surface-700 max-w-2xl mx-auto leading-relaxed">
            Tubevo generates scripts, creates voiceovers, builds videos, and uploads them to your channel — fully automated, powered by AI.
          </motion.p>

          <motion.div variants={fadeUp} className="mt-10 sm:mt-12 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/signup" className="btn-primary !px-8 !py-3.5 text-sm">
              Get Started Free <ArrowRight size={16} />
            </Link>
            <a
              href="#features"
              className="text-sm text-surface-600 hover:text-surface-800 transition-colors duration-200 group"
            >
              See how it works
              <span className="inline-block ml-1 group-hover:translate-x-0.5 transition-transform duration-200">→</span>
            </a>
          </motion.div>
        </motion.div>
      </section>

      {/* ── Features ── */}
      <section id="features" className="max-w-6xl mx-auto px-6 py-24 sm:py-32">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.5, ease }}
          className="flex flex-col items-center text-center mb-20"
        >
          <h2 className="text-3xl sm:text-4xl font-bold text-white mb-5">Everything you need</h2>
          <p className="text-surface-700 max-w-lg mx-auto leading-relaxed">
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
              whileHover={{ y: -4, transition: { duration: 0.25 } }}
              className="card-elevated p-8 group cursor-default"
            >
              <div className={`w-11 h-11 rounded-xl bg-gradient-to-br ${color} flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-300`}>
                <Icon size={20} className={iconColor} />
              </div>
              <h3 className="text-[15px] font-semibold text-white mb-3">{title}</h3>
              <p className="text-sm text-surface-700 leading-relaxed">{desc}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ── Pricing ── */}
      <section id="pricing" className="max-w-5xl mx-auto px-6 py-24 sm:py-32">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.5, ease }}
          className="flex flex-col items-center text-center mb-20"
        >
          <h2 className="text-3xl sm:text-4xl font-bold text-white mb-5">Simple pricing</h2>
          <p className="text-surface-700 leading-relaxed">Start free. Scale when you're ready.</p>
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
              whileHover={{ y: -4, transition: { duration: 0.25 } }}
              className={`relative card-elevated p-8 flex flex-col ${
                tier.popular ? 'border-brand-500/40 ring-1 ring-brand-500/15' : ''
              }`}
            >
              {tier.popular && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 gradient-brand text-white text-xs font-medium px-4 py-1 rounded-full shadow-soft">
                  Most popular
                </span>
              )}
              <h3 className="text-lg font-semibold text-white">{tier.name}</h3>
              <div className="mt-6 mb-8">
                <span className="text-4xl font-bold text-white tracking-tight">{tier.price}</span>
                <span className="text-surface-600 text-sm ml-1">{tier.period}</span>
              </div>
              <ul className="space-y-4 flex-1">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-sm text-surface-700">
                    <Check size={16} className="text-brand-400 mt-0.5 shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
              <Link
                to="/signup"
                className={`mt-8 text-center text-sm font-medium py-3 rounded-xl transition-all duration-250 block ${
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
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-surface-300/30 py-16 text-center">
        <p className="text-sm text-surface-600">© {new Date().getFullYear()} Tubevo. All rights reserved.</p>
        <div className="mt-4 flex items-center justify-center gap-8">
          <Link to="/privacy" className="text-sm text-surface-600 hover:text-surface-800 transition-colors duration-200">Privacy Policy</Link>
          <Link to="/terms" className="text-sm text-surface-600 hover:text-surface-800 transition-colors duration-200">Terms of Service</Link>
        </div>
      </footer>
    </div>
  );
}
