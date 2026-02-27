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
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.3, ease }}
        className={`w-14 h-14 rounded-[10px] flex items-center justify-center mx-auto mb-5 ring-1 ${
          ytConnected
            ? 'bg-emerald-500/8 ring-emerald-500/20'
            : 'bg-red-500/8 ring-red-500/20'
        }`}
      >
        {ytConnected ? (
          <CheckCircle2 size={28} className="text-emerald-400" />
        ) : (
          <Youtube size={28} className="text-red-400" />
        )}
      </motion.div>
      <h2 className="text-lg sm:text-xl font-semibold text-white mb-2">
        {ytConnected ? 'YouTube Connected!' : 'Connect YouTube'}
      </h2>
      <p className="text-surface-600 text-xs mb-7 max-w-sm mx-auto leading-relaxed">
        {ytConnected
          ? `Connected to ${ytChannel}. You're all set to upload videos!`
          : 'Link your YouTube channel so Tubevo can upload videos on your behalf.'}
      </p>
      {ytConnected ? (
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500/8 text-emerald-400 text-xs font-medium">
          <CheckCircle2 size={14} />
          {ytChannel}
        </div>
      ) : (
        <motion.button
          onClick={handleConnectYouTube}
          disabled={ytConnecting}
          whileHover={!ytConnecting ? { scale: 1.02 } : {}}
          whileTap={!ytConnecting ? { scale: 0.98 } : {}}
          className="bg-red-500 hover:bg-red-400 text-white font-medium text-xs px-5 py-2.5 rounded transition-all inline-flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {ytConnecting ? (
            <>
              <Loader2 size={16} className="animate-spin" /> Connecting…
            </>
          ) : (
            <>
              <Youtube size={16} /> Connect with Google
            </>
          )}
        </motion.button>
      )}
      {ytError && (
        <motion.p
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-[11px] text-red-400 mt-2.5 flex items-center justify-center gap-1"
        >
          <AlertTriangle size={11} /> {ytError}
        </motion.p>
      )}
      <p className="text-[11px] text-surface-500 mt-3">
        {ytConnected ? 'You can manage this in Settings.' : 'You can also do this later in Settings.'}
      </p>
    </div>,

    // Step 1: Select niches
    <div key="niche" className="text-center">
      <h2 className="text-lg sm:text-xl font-semibold text-white mb-2">Pick your niches</h2>
      <p className="text-surface-600 text-xs mb-6">Select one or more topics for your channel.</p>
      <div className="flex flex-wrap justify-center gap-2.5 max-w-lg mx-auto max-h-[260px] overflow-y-auto scrollbar-none px-1 py-1">
        {niches.map((n) => {
          const active = selectedNiches.includes(n);
          return (
            <motion.button
              key={n}
              onClick={() => toggleNiche(n)}
              whileTap={{ scale: 0.97 }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                active
                  ? 'bg-brand-500 text-white'
                  : 'bg-surface-200 text-surface-700 hover:bg-surface-300 hover:text-surface-800'
              }`}
            >
              {active && <Check size={12} className="inline mr-1 -mt-0.5" />}
              {n}
            </motion.button>
          );
        })}
      </div>
    </div>,

    // Step 2: Posting frequency
    <div key="freq" className="text-center">
      <h2 className="text-lg sm:text-xl font-semibold text-white mb-2">Posting frequency</h2>
      <p className="text-surface-600 text-xs mb-7">How often should Tubevo publish videos?</p>
      <div className="space-y-2.5 max-w-xs mx-auto">
        {frequencies.map((f) => (
          <motion.button
            key={f.value}
            onClick={() => setFrequency(f.value)}
            whileTap={{ scale: 0.99 }}
            className={`w-full text-left px-4 py-3 rounded-lg transition-all ${
              frequency === f.value
                ? 'bg-brand-500/8 text-white'
                : 'bg-surface-200/60 text-surface-700 hover:bg-surface-300/60'
            }`}
          >
            <span className="text-xs font-semibold flex items-center gap-2">
              {f.label}
              {frequency === f.value && (
                <motion.span
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="inline-flex"
                >
                  <Check size={12} className="text-brand-400" />
                </motion.span>
              )}
            </span>
            <span className="block text-[11px] text-surface-500 mt-0.5">{f.desc}</span>
          </motion.button>
        ))}
      </div>
    </div>,

    // Step 3: Confirmation
    <div key="confirm" className="text-center">
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.3, ease }}
        className="w-14 h-14 rounded-[10px] bg-brand-500 flex items-center justify-center mx-auto mb-5"
      >
        <Rocket size={28} className="text-white" />
      </motion.div>
      <h2 className="text-lg sm:text-xl font-semibold text-white mb-2">You're all set!</h2>
      <p className="text-surface-600 text-xs mb-6 max-w-sm mx-auto leading-relaxed">
        Tubevo will start generating and posting content based on your preferences.
      </p>
      <div className="card p-5 max-w-xs mx-auto text-left space-y-3 mb-7">
        <div className="flex justify-between text-xs">
          <span className="text-surface-500 uppercase tracking-wider text-[10px] font-semibold">Niches</span>
          <span className="text-white font-medium text-right max-w-[60%] truncate">{selectedNiches.join(', ') || 'None'}</span>
        </div>
        <div className="h-px bg-white/4" />
        <div className="flex justify-between text-xs">
          <span className="text-surface-500 uppercase tracking-wider text-[10px] font-semibold">Frequency</span>
          <span className="text-white font-medium capitalize">{frequency.replace('_', ' ') || 'Not set'}</span>
        </div>
      </div>
      <motion.button
        onClick={launch}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        className="btn-primary inline-flex items-center gap-2 px-6 py-2.5 text-xs"
      >
        <Rocket size={14} /> Launch Tubevo
      </motion.button>
    </div>,
  ];

  return (
    <div className="min-h-screen bg-surface-50 flex items-center justify-center px-4 relative overflow-hidden">
      {/* Ambient background glows — subtle */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[500px] bg-brand-600/3 rounded-full blur-[120px] pointer-events-none" />

      <div className="w-full max-w-[480px] relative z-10">
        {/* Progress — step circles + progress bar */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {[0, 1, 2, 3].map((i) => (
            <motion.div
              key={i}
              animate={{
                scale: i === step ? 1.1 : 1,
                opacity: i <= step ? 1 : 0.3,
              }}
              transition={{ duration: 0.25, ease }}
              className={`w-[8px] h-[8px] rounded-full ${
                i <= step ? 'bg-brand-500' : 'bg-surface-400'
              }`}
            />
          ))}
          <span className="text-[10px] text-surface-600 font-semibold tracking-wider ml-3 tabular-nums">
            {String(step + 1).padStart(2, '0')} / 04
          </span>
        </div>

        {/* Progress bar */}
        <div className="w-full h-[3px] bg-surface-300/40 rounded-full overflow-hidden mb-8">
          <motion.div
            className="h-full rounded-full bg-brand-500"
            animate={{ width: `${((step + 1) / 4) * 100}%` }}
            transition={{ duration: 0.4, ease }}
          />
        </div>

        {/* Content Card */}
        <div className="card p-8 sm:p-10 !rounded-[20px] min-h-[340px] sm:min-h-[380px] flex items-center justify-center overflow-hidden">
          <AnimatePresence mode="wait" custom={direction}>
            <motion.div
              key={step}
              custom={direction}
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.25, ease }}
              className="w-full"
            >
              {steps[step]}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-6">
          <motion.button
            onClick={back}
            disabled={step === 0}
            whileTap={{ scale: 0.97 }}
            className="text-xs text-surface-500 hover:text-white disabled:opacity-20 disabled:cursor-not-allowed transition-colors flex items-center gap-1 font-medium"
          >
            <ArrowLeft size={12} /> Back
          </motion.button>
          {step < 3 && (
            <motion.button
              onClick={next}
              whileTap={{ scale: 0.97 }}
              className="text-xs text-brand-400 hover:text-brand-300 transition-colors flex items-center gap-1 font-medium"
            >
              {step === 0 ? 'Skip for now' : 'Next'} <ArrowRight size={12} />
            </motion.button>
          )}
        </div>
      </div>
    </div>
  );
}
