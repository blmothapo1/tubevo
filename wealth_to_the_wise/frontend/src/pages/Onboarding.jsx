import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Youtube, Check, ArrowRight, ArrowLeft, Rocket } from 'lucide-react';

const niches = ['Personal Finance', 'Fitness', 'Productivity', 'Motivation', 'Nutrition'];
const frequencies = [
  { value: 'daily', label: 'Daily', desc: '1 video per day' },
  { value: 'every_2_days', label: 'Every 2 Days', desc: '3–4 videos per week' },
  { value: 'weekly', label: 'Weekly', desc: '1 video per week' },
];

export default function Onboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [selectedNiches, setSelectedNiches] = useState([]);
  const [frequency, setFrequency] = useState('');

  function toggleNiche(n) {
    setSelectedNiches((prev) =>
      prev.includes(n) ? prev.filter((x) => x !== n) : [...prev, n]
    );
  }

  function next() { setStep((s) => Math.min(s + 1, 3)); }
  function back() { setStep((s) => Math.max(s - 1, 0)); }

  function launch() {
    // TODO: POST onboarding data to backend when API endpoints exist
    navigate('/dashboard');
  }

  const steps = [
    // Step 0: Connect YouTube
    <div key="yt" className="text-center">
      <div className="w-16 h-16 rounded-2xl bg-red-500/10 flex items-center justify-center mx-auto mb-6 ring-1 ring-red-500/20">
        <Youtube size={32} className="text-red-400" />
      </div>
      <h2 className="text-2xl font-bold text-white mb-2">Connect YouTube</h2>
      <p className="text-surface-700 text-sm mb-8 max-w-sm mx-auto">
        Link your YouTube channel so Tubevo can upload videos on your behalf.
      </p>
      <button className="bg-red-500 hover:bg-red-400 text-white font-medium text-sm px-6 py-3 rounded-lg transition-all inline-flex items-center gap-2 shadow-lg shadow-red-500/20">
        <Youtube size={18} /> Connect with Google
      </button>
      <p className="text-xs text-surface-600 mt-4">You can also do this later in Settings.</p>
    </div>,

    // Step 1: Select niches
    <div key="niche" className="text-center">
      <h2 className="text-2xl font-bold text-white mb-2">Pick your niches</h2>
      <p className="text-surface-700 text-sm mb-8">Select one or more topics for your channel.</p>
      <div className="flex flex-wrap justify-center gap-3 max-w-md mx-auto">
        {niches.map((n) => {
          const active = selectedNiches.includes(n);
          return (
            <button
              key={n}
              onClick={() => toggleNiche(n)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-all border ${
                active
                  ? 'gradient-brand border-brand-500 text-white shadow-md shadow-brand-500/20'
                  : 'bg-surface-200 border-surface-400 text-surface-700 hover:border-surface-500 hover:text-surface-800'
              }`}
            >
              {active && <Check size={14} className="inline mr-1.5 -mt-0.5" />}
              {n}
            </button>
          );
        })}
      </div>
    </div>,

    // Step 2: Posting frequency
    <div key="freq" className="text-center">
      <h2 className="text-2xl font-bold text-white mb-2">Posting frequency</h2>
      <p className="text-surface-700 text-sm mb-8">How often should Tubevo publish videos?</p>
      <div className="space-y-3 max-w-xs mx-auto">
        {frequencies.map((f) => (
          <button
            key={f.value}
            onClick={() => setFrequency(f.value)}
            className={`w-full text-left px-4 py-3 rounded-xl border transition-all ${
              frequency === f.value
                ? 'bg-brand-600/15 border-brand-500 text-white shadow-md shadow-brand-500/10'
                : 'bg-surface-200 border-surface-400 text-surface-700 hover:border-surface-500'
            }`}
          >
            <span className="text-sm font-medium">{f.label}</span>
            {frequency === f.value && (
              <Check size={14} className="inline ml-2 text-brand-400 -mt-0.5" />
            )}
            <span className="block text-xs text-surface-600 mt-0.5">{f.desc}</span>
          </button>
        ))}
      </div>
    </div>,

    // Step 3: Confirmation
    <div key="confirm" className="text-center">
      <div className="w-16 h-16 rounded-2xl gradient-brand flex items-center justify-center mx-auto mb-6 glow-brand">
        <Rocket size={32} className="text-white" />
      </div>
      <h2 className="text-2xl font-bold text-white mb-2">You're all set!</h2>
      <p className="text-surface-700 text-sm mb-4 max-w-sm mx-auto">
        Tubevo will start generating and posting content based on your preferences.
      </p>
      <div className="bg-surface-200 rounded-xl p-4 max-w-xs mx-auto text-left space-y-2 mb-8 border border-surface-300">
        <div className="flex justify-between text-sm">
          <span className="text-surface-600">Niches</span>
          <span className="text-white font-medium">{selectedNiches.join(', ') || 'None'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-surface-600">Frequency</span>
          <span className="text-white font-medium capitalize">{frequency.replace('_', ' ') || 'Not set'}</span>
        </div>
      </div>
      <button
        onClick={launch}
        className="gradient-brand hover:opacity-90 text-white font-medium text-sm px-8 py-3 rounded-lg transition-all inline-flex items-center gap-2 glow-brand"
      >
        <Rocket size={16} /> Launch Tubevo
      </button>
    </div>,
  ];

  return (
    <div className="min-h-screen bg-surface-50 flex items-center justify-center px-4 relative overflow-hidden">
      {/* Decorative glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[500px] bg-brand-600/5 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-lg relative z-10">
        {/* Progress */}
        <div className="flex items-center justify-center gap-2 mb-10">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className={`h-1.5 rounded-full transition-all ${
                i <= step ? 'w-10 gradient-brand' : 'w-6 bg-surface-400'
              }`}
            />
          ))}
        </div>

        {/* Content */}
        <div className="bg-surface-100 border border-surface-300 rounded-2xl p-8 min-h-[360px] flex items-center justify-center">
          {steps[step]}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-6">
          <button
            onClick={back}
            disabled={step === 0}
            className="text-sm text-surface-600 hover:text-surface-900 disabled:opacity-30 disabled:cursor-not-allowed transition-colors flex items-center gap-1"
          >
            <ArrowLeft size={14} /> Back
          </button>
          {step < 3 && (
            <button
              onClick={next}
              className="text-sm text-brand-400 hover:text-brand-300 transition-colors flex items-center gap-1"
            >
              {step === 0 ? 'Skip for now' : 'Next'} <ArrowRight size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
