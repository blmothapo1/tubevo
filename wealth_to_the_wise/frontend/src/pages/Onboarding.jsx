import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Youtube, Check, ArrowRight, ArrowLeft, Rocket, Sparkles, Loader2, CheckCircle2, AlertTriangle } from 'lucide-react';
import api from '../lib/api';

const ease = [0.25, 0.1, 0.25, 1];

const niches = [
  'Personal Finance',
  'Investing / Stocks',
  'Business & Entrepreneurship',
  'Self-Improvement',
  'Psychology',
  'Productivity',
  'Tech & AI',
  'True Crime',
  'Horror Stories',
  'Mystery & Conspiracy',
  'History',
  'Science & Space',
  'Fitness & Health',
  'Luxury & Wealth',
  'Geography & World Facts',
];
const frequencies = [
  { value: 'daily', label: 'Daily', desc: '1 video per day' },
  { value: 'every_2_days', label: 'Every 2 Days', desc: '3–4 videos per week' },
  { value: 'weekly', label: 'Weekly', desc: '1 video per week' },
];

const slideVariants = {
  enter: (direction) => ({ x: direction > 0 ? 80 : -80, opacity: 0, scale: 0.96 }),
  center: { x: 0, opacity: 1, scale: 1 },
  exit: (direction) => ({ x: direction < 0 ? 80 : -80, opacity: 0, scale: 0.96 }),
};

export default function Onboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(0);
  const [selectedNiches, setSelectedNiches] = useState([]);
  const [frequency, setFrequency] = useState('');

  // YouTube connection state
  const [ytConnecting, setYtConnecting] = useState(false);
  const [ytConnected, setYtConnected] = useState(false);
  const [ytChannel, setYtChannel] = useState('');
  const [ytError, setYtError] = useState('');

  // Check if YouTube is already connected on mount
  useEffect(() => {
    async function checkYt() {
      try {
        const { data } = await api.get('/oauth/youtube/status');
        if (data?.connected) {
          setYtConnected(true);
          setYtChannel(data.channel_title || 'YouTube Connected');
        }
      } catch {
        // Not connected — expected for new users
      }
    }
    checkYt();
  }, []);

  async function handleConnectYouTube() {
    setYtConnecting(true);
    setYtError('');
    try {
      const { data } = await api.get('/oauth/youtube/authorize');
      // Remember we came from onboarding so GoogleCallback redirects back here
      localStorage.setItem('yt_connect_origin', 'onboarding');
      // Redirect to Google consent screen — user comes back via GoogleCallback
      window.location.href = data.auth_url;
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 503) {
        setYtError('YouTube integration is not configured yet.');
      } else {
        setYtError(detail || 'Failed to start YouTube connection. Try again.');
      }
      setYtConnecting(false);
    }
  }

  function toggleNiche(n) {
    setSelectedNiches((prev) =>
      prev.includes(n) ? prev.filter((x) => x !== n) : [...prev, n]
    );
  }

  function next() {
    setDirection(1);
    setStep((s) => Math.min(s + 1, 3));
  }
  function back() {
    setDirection(-1);
    setStep((s) => Math.max(s - 1, 0));
  }

  function launch() {
    navigate('/dashboard');
  }

  const steps = [
    // Step 0: Connect YouTube
    <div key="yt" className="text-center">
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.5, ease }}
        className={`w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6 ring-1 shadow-lg ${
          ytConnected
            ? 'bg-emerald-500/10 ring-emerald-500/20 shadow-emerald-500/10'
            : 'bg-red-500/10 ring-red-500/20 shadow-red-500/10'
        }`}
      >
        {ytConnected ? (
          <CheckCircle2 size={32} className="text-emerald-400" />
        ) : (
          <Youtube size={32} className="text-red-400" />
        )}
      </motion.div>
      <h2 className="text-xl sm:text-2xl font-bold text-white mb-2">
        {ytConnected ? 'YouTube Connected!' : 'Connect YouTube'}
      </h2>
      <p className="text-surface-600 text-sm mb-8 max-w-sm mx-auto leading-relaxed">
        {ytConnected
          ? `Connected to ${ytChannel}. You're all set to upload videos!`
          : 'Link your YouTube channel so Tubevo can upload videos on your behalf.'}
      </p>
      {ytConnected ? (
        <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm font-medium">
          <CheckCircle2 size={16} />
          {ytChannel}
        </div>
      ) : (
        <motion.button
          onClick={handleConnectYouTube}
          disabled={ytConnecting}
          whileHover={!ytConnecting ? { scale: 1.03, y: -1 } : {}}
          whileTap={!ytConnecting ? { scale: 0.97 } : {}}
          className="bg-red-500 hover:bg-red-400 text-white font-medium text-sm px-6 py-3 rounded-xl transition-all inline-flex items-center gap-2 shadow-lg shadow-red-500/25 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {ytConnecting ? (
            <>
              <Loader2 size={18} className="animate-spin" /> Connecting…
            </>
          ) : (
            <>
              <Youtube size={18} /> Connect with Google
            </>
          )}
        </motion.button>
      )}
      {ytError && (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-xs text-red-400 mt-3 flex items-center justify-center gap-1.5"
        >
          <AlertTriangle size={12} /> {ytError}
        </motion.p>
      )}
      <p className="text-xs text-surface-500 mt-4">
        {ytConnected ? 'You can manage this in Settings.' : 'You can also do this later in Settings.'}
      </p>
    </div>,

    // Step 1: Select niches
    <div key="niche" className="text-center">
      <h2 className="text-xl sm:text-2xl font-bold text-white mb-2">Pick your niches</h2>
      <p className="text-surface-600 text-sm mb-6">Select one or more topics for your channel.</p>
      <div className="flex flex-wrap justify-center gap-2.5 max-w-lg mx-auto max-h-[280px] overflow-y-auto scrollbar-none px-1 py-1">
        {niches.map((n) => {
          const active = selectedNiches.includes(n);
          return (
            <motion.button
              key={n}
              onClick={() => toggleNiche(n)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-all border ${
                active
                  ? 'bg-gradient-to-r from-brand-500 to-brand-600 border-brand-500/50 text-white shadow-md shadow-brand-500/20'
                  : 'bg-surface-200/80 border-surface-300/60 text-surface-700 hover:border-surface-400 hover:text-surface-800'
              }`}
            >
              {active && <Check size={14} className="inline mr-1.5 -mt-0.5" />}
              {n}
            </motion.button>
          );
        })}
      </div>
    </div>,

    // Step 2: Posting frequency
    <div key="freq" className="text-center">
      <h2 className="text-xl sm:text-2xl font-bold text-white mb-2">Posting frequency</h2>
      <p className="text-surface-600 text-sm mb-8">How often should Tubevo publish videos?</p>
      <div className="space-y-3 max-w-xs mx-auto">
        {frequencies.map((f) => (
          <motion.button
            key={f.value}
            onClick={() => setFrequency(f.value)}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className={`w-full text-left px-5 py-4 rounded-xl border transition-all ${
              frequency === f.value
                ? 'bg-brand-600/10 border-brand-500/50 text-white shadow-md shadow-brand-500/10'
                : 'bg-surface-200/60 border-surface-300/50 text-surface-700 hover:border-surface-400'
            }`}
          >
            <span className="text-sm font-semibold flex items-center gap-2">
              {f.label}
              {frequency === f.value && (
                <motion.span
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="inline-flex"
                >
                  <Check size={14} className="text-brand-400" />
                </motion.span>
              )}
            </span>
            <span className="block text-xs text-surface-500 mt-1">{f.desc}</span>
          </motion.button>
        ))}
      </div>
    </div>,

    // Step 3: Confirmation
    <div key="confirm" className="text-center">
      <motion.div
        initial={{ scale: 0.8, opacity: 0, rotate: -10 }}
        animate={{ scale: 1, opacity: 1, rotate: 0 }}
        transition={{ duration: 0.5, ease }}
        className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center mx-auto mb-6 shadow-lg shadow-brand-500/30"
      >
        <Rocket size={32} className="text-white" />
      </motion.div>
      <h2 className="text-xl sm:text-2xl font-bold text-white mb-2">You're all set!</h2>
      <p className="text-surface-600 text-sm mb-6 max-w-sm mx-auto leading-relaxed">
        Tubevo will start generating and posting content based on your preferences.
      </p>
      <div className="card p-5 max-w-xs mx-auto text-left space-y-3 mb-8">
        <div className="flex justify-between text-sm">
          <span className="text-surface-500">Niches</span>
          <span className="text-white font-medium text-right max-w-[60%] truncate">{selectedNiches.join(', ') || 'None'}</span>
        </div>
        <div className="h-px bg-surface-300/30" />
        <div className="flex justify-between text-sm">
          <span className="text-surface-500">Frequency</span>
          <span className="text-white font-medium capitalize">{frequency.replace('_', ' ') || 'Not set'}</span>
        </div>
      </div>
      <motion.button
        onClick={launch}
        whileHover={{ scale: 1.03, y: -1 }}
        whileTap={{ scale: 0.97 }}
        className="btn-primary inline-flex items-center gap-2 px-8 py-3.5 text-sm"
      >
        <Rocket size={16} /> Launch Tubevo
      </motion.button>
    </div>,
  ];

  return (
    <div className="min-h-screen bg-surface-50 flex items-center justify-center px-4 relative overflow-hidden">
      {/* Ambient background glows */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-brand-600/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-[400px] h-[400px] bg-accent-500/3 rounded-full blur-[100px] pointer-events-none" />

      <div className="w-full max-w-lg relative z-10">
        {/* Progress */}
        <div className="flex items-center justify-center gap-2 mb-10">
          {[0, 1, 2, 3].map((i) => (
            <motion.div
              key={i}
              animate={{
                width: i <= step ? 40 : 24,
                opacity: i <= step ? 1 : 0.4,
              }}
              transition={{ duration: 0.4, ease }}
              className={`h-1.5 rounded-full ${
                i <= step ? 'bg-gradient-to-r from-brand-500 to-brand-400' : 'bg-surface-400'
              }`}
            />
          ))}
        </div>

        {/* Content Card */}
        <div className="card-elevated p-6 sm:p-10 min-h-[360px] sm:min-h-[400px] flex items-center justify-center overflow-hidden">
          <AnimatePresence mode="wait" custom={direction}>
            <motion.div
              key={step}
              custom={direction}
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.35, ease }}
              className="w-full"
            >
              {steps[step]}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-8">
          <motion.button
            onClick={back}
            disabled={step === 0}
            whileHover={{ x: -2 }}
            whileTap={{ scale: 0.95 }}
            className="text-sm text-surface-500 hover:text-white disabled:opacity-20 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5 font-medium"
          >
            <ArrowLeft size={14} /> Back
          </motion.button>
          {step < 3 && (
            <motion.button
              onClick={next}
              whileHover={{ x: 2 }}
              whileTap={{ scale: 0.95 }}
              className="text-sm text-brand-400 hover:text-brand-300 transition-colors flex items-center gap-1.5 font-medium"
            >
              {step === 0 ? 'Skip for now' : 'Next'} <ArrowRight size={14} />
            </motion.button>
          )}
        </div>
      </div>
    </div>
  );
}
