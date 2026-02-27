import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { FadeIn } from '../components/Motion';
import { SkeletonLine, SkeletonCard } from '../components/Skeleton';
import {
  Save,
  Youtube,
  Bell,
  CreditCard,
  BarChart3,
  Key,
  Check,
  Shield,
  Zap,
  ExternalLink,
  User,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  ArrowRight,
  HelpCircle,
  Sparkles,
  CircleDot,
  CheckCircle2,
  PlayCircle,
  Film,
  Type,
  Volume2,
  Sun,
  Moon,
  Monitor,
} from 'lucide-react';
import useOnboarding from '../hooks/useOnboarding';
import { getStoredPreference, setPreference as setThemePreference } from '../theme/theme';

const ease = [0.25, 0.1, 0.25, 1];

const tabs = [
  { key: 'account', label: 'Account', icon: User },
  { key: 'apikeys', label: 'API Keys', icon: Key },
  { key: 'video', label: 'Video', icon: Film },
  { key: 'youtube', label: 'YouTube', icon: Youtube },
  { key: 'notifications', label: 'Notifications', icon: Bell },
  { key: 'plan', label: 'Plan', icon: CreditCard },
  { key: 'usage', label: 'API Usage', icon: BarChart3 },
];

export default function Settings() {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState(() => {
    const tabParam = searchParams.get('tab');
    return tabs.some((t) => t.key === tabParam) ? tabParam : 'account';
  });
  const [fullName, setFullName] = useState(user?.full_name || '');
  const [email] = useState(user?.email || '');

  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam && tabs.some((t) => t.key === tabParam)) {
      setActiveTab(tabParam);
    }
  }, [searchParams]);

  return (
    <FadeIn className="max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-[20px] sm:text-[24px] font-semibold text-white tracking-tight">Settings</h1>
        <p className="text-[12px] text-surface-600 mt-2 uppercase tracking-[0.08em] font-medium">Manage your account and preferences</p>
      </div>

      {/* Pill-style Tabs */}
      <div className="flex gap-1 bg-surface-100 rounded-[10px] p-1.5 overflow-x-auto scrollbar-none">
        {tabs.map(({ key, label, icon: Icon }) => (
          <motion.button
            key={key}
            onClick={() => setActiveTab(key)}
            whileTap={{ scale: 0.98 }}
            {...(key === 'apikeys' ? { 'data-tour': 'settings-apikeys-tab' } : {})}
            className={`relative flex items-center gap-2 px-3.5 sm:px-4 h-[36px] rounded-[8px] text-[11px] sm:text-[12px] font-medium transition-all whitespace-nowrap ${
              activeTab === key
                ? 'text-white'
                : 'text-surface-600 hover:text-surface-800 hover:bg-white/[0.04]'
            }`}
          >
            {activeTab === key && (
              <motion.div
                layoutId="settings-tab-bg"
                className="absolute inset-0 bg-surface-300 rounded-[8px]"
                transition={{ type: 'tween', duration: 0.2, ease: 'easeOut' }}
              />
            )}
            <span className="relative z-10 flex items-center gap-1.5">
              <Icon size={14} />
              <span className="hidden sm:inline">{label}</span>
            </span>
          </motion.button>
        ))}
      </div>

      {/* Tab Content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.2, ease }}
          className="card p-8"
        >
          {activeTab === 'account' && (
            <AccountTab fullName={fullName} setFullName={setFullName} email={email} />
          )}
          {activeTab === 'apikeys' && <ApiKeysTab />}
          {activeTab === 'video' && <VideoPreferencesTab />}
          {activeTab === 'youtube' && <YouTubeTab />}
          {activeTab === 'notifications' && <NotificationsTab />}
          {activeTab === 'plan' && <PlanTab plan={user?.plan || 'free'} />}
          {activeTab === 'usage' && <UsageTab />}
        </motion.div>
      </AnimatePresence>
    </FadeIn>
  );
}

/* ── Account ─────────────────────────────────────────────────── */
function AccountTab({ fullName, setFullName, email }) {
  const { fetchUser } = useAuth();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  async function handleSave() {
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      await api.patch('/auth/me', { full_name: fullName });
      await fetchUser();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-7 max-w-md">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-[10px] bg-brand-500/10 flex items-center justify-center">
          <User size={16} className="text-brand-400" />
        </div>
        <div>
          <h3 className="text-[15px] font-semibold text-white">Account Details</h3>
          <p className="text-[12px] text-surface-600 mt-0.5">Update your profile information</p>
        </div>
      </div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-red-500/6 text-red-400 text-xs px-3 py-2.5 rounded-lg"
          >
            {error}
          </motion.div>
        )}
        {saved && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-emerald-500/6 text-emerald-400 text-xs px-3 py-2.5 rounded-lg flex items-center gap-2"
          >
            <Check size={14} /> Changes saved successfully.
          </motion.div>
        )}
      </AnimatePresence>

      <div>
        <label className="block text-[10px] font-semibold text-surface-500 mb-2 uppercase tracking-wider">Full Name</label>
        <input
          type="text"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="input-premium w-full"
        />
      </div>
      <div>
        <label className="block text-[10px] font-semibold text-surface-500 mb-2 uppercase tracking-wider">Email</label>
        <input
          type="email"
          value={email}
          disabled
          className="input-premium w-full opacity-45 cursor-not-allowed"
        />
        <p className="text-[11px] text-surface-500 mt-1.5">Email cannot be changed.</p>
      </div>
      <motion.button
        onClick={handleSave}
        disabled={saving}
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        className="btn-primary flex items-center gap-2 px-5 py-2"
      >
        {saving ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
        {saving ? 'Saving…' : 'Save Changes'}
      </motion.button>

      {/* Replay Tutorial — additive section */}
      <ReplayTutorialSection />

      {/* Appearance — theme toggle */}
      <AppearanceSection />
    </div>
  );
}

/* ── Replay Tutorial ──────────────────────────────────────────── */
function ReplayTutorialSection() {
  const { replayTutorial } = useOnboarding();

  return (
    <div className="pt-6 mt-6">
      <div className="flex items-center gap-4 mb-4">
        <div className="w-10 h-10 rounded-[10px] bg-brand-500/10 flex items-center justify-center">
          <PlayCircle size={16} className="text-brand-400" />
        </div>
        <div>
          <h3 className="text-[14px] font-semibold text-white">Guided Tutorial</h3>
          <p className="text-[12px] text-surface-600 mt-0.5">Walk through the app features step by step</p>
        </div>
      </div>
      <motion.button
        onClick={replayTutorial}
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium text-brand-400 bg-brand-500/8 hover:bg-brand-500/15 transition-colors"
      >
        <PlayCircle size={16} />
        Replay Tutorial
      </motion.button>
    </div>
  );
}

/* ── Appearance — Theme Toggle ─────────────────────────────────── */
const THEME_OPTIONS = [
  { key: 'system', label: 'System', icon: Monitor },
  { key: 'dark', label: 'Dark', icon: Moon },
  { key: 'light', label: 'Light', icon: Sun },
];

function AppearanceSection() {
  const [pref, setPref] = useState(getStoredPreference);

  function handleChange(key) {
    setPref(key);
    setThemePreference(key);
  }

  return (
    <div className="pt-6 mt-6">
      <div className="flex items-center gap-4 mb-4">
        <div className="w-10 h-10 rounded-[10px] bg-brand-500/10 flex items-center justify-center">
          <Sun size={16} className="text-brand-400" />
        </div>
        <div>
          <h3 className="text-[14px] font-semibold text-white">Appearance</h3>
          <p className="text-[12px] text-surface-600 mt-0.5">Choose your preferred theme</p>
        </div>
      </div>
      <div className="flex gap-1.5 p-1.5 rounded-[10px] bg-surface-100 w-fit">
        {THEME_OPTIONS.map(({ key, label, icon: Icon }) => (
          <motion.button
            key={key}
            onClick={() => handleChange(key)}
            whileTap={{ scale: 0.97 }}
            className={`relative flex items-center gap-1.5 px-3 py-1.5 rounded-[8px] text-[12px] font-medium transition-colors ${
              pref === key
                ? 'text-white bg-surface-300'
                : 'text-surface-600 hover:text-surface-800'
            }`}
          >
            <Icon size={14} />
            {label}
          </motion.button>
        ))}
      </div>
    </div>
  );
}

/* ── API Keys (BYOK) — Guided Setup ──────────────────────────── */

const PROVIDER_URLS = {
  openai: 'https://platform.openai.com/api-keys',
  elevenlabs: 'https://elevenlabs.io/app/settings/api-keys',
  pexels: 'https://www.pexels.com/api/new/',
};

const KEY_PREFIXES = {
  openai: 'sk-',
  elevenlabs: 'sk_',
};

function ApiKeysTab() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [keyStatus, setKeyStatus] = useState(null);
  const [form, setForm] = useState({
    openai_api_key: '',
    elevenlabs_api_key: '',
    elevenlabs_voice_id: '',
    pexels_api_key: '',
  });
  const [fieldErrors, setFieldErrors] = useState({});

  useEffect(() => {
    async function fetchKeys() {
      try {
        const { data } = await api.get('/api/keys');
        setKeyStatus(data);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    }
    fetchKeys();
  }, []);

  function validateFields() {
    const errs = {};
    if (form.openai_api_key && !form.openai_api_key.startsWith('sk-')) {
      errs.openai_api_key = 'OpenAI keys usually start with "sk-"';
    }
    if (form.elevenlabs_api_key && form.elevenlabs_api_key.length < 10) {
      errs.elevenlabs_api_key = 'This key looks too short';
    }
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleSave() {
    if (!validateFields()) return;
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      const payload = {};
      if (form.openai_api_key) payload.openai_api_key = form.openai_api_key;
      if (form.elevenlabs_api_key) payload.elevenlabs_api_key = form.elevenlabs_api_key;
      if (form.elevenlabs_voice_id) payload.elevenlabs_voice_id = form.elevenlabs_voice_id;
      if (form.pexels_api_key) payload.pexels_api_key = form.pexels_api_key;

      if (Object.keys(payload).length === 0) {
        setError('Enter at least one key to save.');
        setSaving(false);
        return;
      }

      const { data } = await api.put('/api/keys', payload);
      setKeyStatus(data);
      setForm({ openai_api_key: '', elevenlabs_api_key: '', elevenlabs_voice_id: '', pexels_api_key: '' });
      setFieldErrors({});
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save keys.');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 max-w-xl">
        <SkeletonLine width="w-40" />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  const allKeysSet = keyStatus?.has_openai_key && keyStatus?.has_elevenlabs_key;
  const steps = [
    { label: 'Add OpenAI key', done: !!keyStatus?.has_openai_key, field: 'openai' },
    { label: 'Add ElevenLabs key', done: !!keyStatus?.has_elevenlabs_key, field: 'elevenlabs' },
    { label: 'Add Pexels key', done: !!keyStatus?.has_pexels_key, field: 'pexels', optional: true },
  ];

  return (
    <div className="space-y-7 max-w-xl">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-[10px] bg-amber-500/10 flex items-center justify-center">
          <Key size={16} className="text-amber-400" />
        </div>
        <div>
          <h3 className="text-[15px] font-semibold text-white">Your API Keys</h3>
          <p className="text-[12px] text-surface-600 mt-0.5">
            A private password that lets Tubevo use AI services on your behalf.
          </p>
        </div>
      </div>

      {/* Setup checklist */}
      <div className="card p-5 space-y-3">
        <p className="text-[10px] font-semibold text-surface-500 uppercase tracking-widest mb-1">Setup Checklist</p>
        {steps.map((s, i) => (
          <div key={i} className="flex items-center gap-2.5">
            {s.done ? (
              <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
            ) : (
              <CircleDot size={14} className="text-surface-500 shrink-0" />
            )}
            <span className={`text-xs ${s.done ? 'text-emerald-400 line-through' : 'text-white'}`}>
              {s.label}
              {s.optional && <span className="text-surface-500 text-[11px] ml-1">(optional)</span>}
            </span>
          </div>
        ))}
        {allKeysSet && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="pt-1.5"
          >
            <a
              href="/videos"
              className="btn-primary inline-flex items-center gap-2 px-4 py-2 text-xs w-full justify-center"
            >
              <Sparkles size={14} /> Start Creating Videos <ArrowRight size={12} />
            </a>
          </motion.div>
        )}
      </div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-red-500/6 text-red-400 text-xs px-3 py-2.5 rounded-lg"
          >
            {error}
          </motion.div>
        )}
        {saved && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-emerald-500/6 text-emerald-400 text-xs px-3 py-2.5 rounded-lg flex items-center gap-2"
          >
            <Check size={14} /> Keys saved and encrypted securely.
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input fields with "Get Key" buttons */}
      <div className="space-y-7">
        <KeyInput
          label="OpenAI API Key"
          required
          value={form.openai_api_key}
          onChange={(v) => { setForm({ ...form, openai_api_key: v }); setFieldErrors({ ...fieldErrors, openai_api_key: '' }); }}
          placeholder={keyStatus?.has_openai_key ? `Current: ${keyStatus.openai_key_hint || '••••'}` : 'sk-proj-...'}
          providerUrl={PROVIDER_URLS.openai}
          providerName="OpenAI"
          fieldError={fieldErrors.openai_api_key}
          isSet={keyStatus?.has_openai_key}
          hint={keyStatus?.openai_key_hint}
          helpSteps={[
            'Go to platform.openai.com and sign in (or create a free account)',
            'Click your profile → "API keys" → "Create new secret key"',
            'Copy the key and paste it below',
          ]}
        />
        <KeyInput
          label="ElevenLabs API Key"
          required
          value={form.elevenlabs_api_key}
          onChange={(v) => { setForm({ ...form, elevenlabs_api_key: v }); setFieldErrors({ ...fieldErrors, elevenlabs_api_key: '' }); }}
          placeholder={keyStatus?.has_elevenlabs_key ? `Current: ${keyStatus.elevenlabs_key_hint || '••••'}` : 'sk_...'}
          providerUrl={PROVIDER_URLS.elevenlabs}
          providerName="ElevenLabs"
          fieldError={fieldErrors.elevenlabs_api_key}
          isSet={keyStatus?.has_elevenlabs_key}
          hint={keyStatus?.elevenlabs_key_hint}
          helpSteps={[
            'Go to elevenlabs.io and sign in (or create an account)',
            'Click your profile icon → "Profile + API key"',
            'Copy the API key and paste it below',
          ]}
        />
        <div>
          <label className="block text-xs font-medium text-surface-500 mb-2">
            ElevenLabs Voice ID <span className="text-surface-500/60">(optional)</span>
          </label>
          <input
            type="text"
            value={form.elevenlabs_voice_id}
            onChange={(e) => setForm({ ...form, elevenlabs_voice_id: e.target.value })}
            placeholder={keyStatus?.elevenlabs_voice_id || 'e.g. pNInz6obpgDQGcFmaJgB'}
            className="input-premium w-full mono"
          />
          <p className="text-[11px] text-surface-500 mt-1">Leave blank to use the default voice.</p>
        </div>
        <KeyInput
          label="Pexels API Key"
          value={form.pexels_api_key}
          onChange={(v) => setForm({ ...form, pexels_api_key: v })}
          placeholder={keyStatus?.has_pexels_key ? `Current: ${keyStatus.pexels_key_hint || '••••'}` : 'Free at pexels.com/api'}
          providerUrl={PROVIDER_URLS.pexels}
          providerName="Pexels"
          isSet={keyStatus?.has_pexels_key}
          hint={keyStatus?.pexels_key_hint}
          optional
          helpSteps={[
            'Go to pexels.com/api and click "Your API Key"',
            'Sign up (free) or log in, then copy the key',
            'Paste it below — Pexels provides free stock footage for your videos',
          ]}
        />
      </div>

      <motion.button
        onClick={handleSave}
        disabled={saving}
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        className="btn-primary flex items-center gap-2 px-5 py-2 w-full justify-center text-xs"
      >
        {saving ? <RefreshCw size={14} className="animate-spin" /> : <Shield size={14} />}
        {saving ? 'Encrypting & saving…' : 'Save API Keys'}
      </motion.button>

      <div className="card p-4 flex items-start gap-3">
        <Shield size={14} className="text-brand-400 shrink-0 mt-0.5" />
        <p className="text-[12px] text-surface-600 leading-[1.7]">
          <strong className="text-surface-700">Keys are encrypted</strong> and stored securely.
          Only used to generate videos on your behalf. You pay each provider directly.
        </p>
      </div>
    </div>
  );
}

function KeyInput({ label, required, optional, value, onChange, placeholder, providerUrl, providerName, fieldError, isSet, hint, helpSteps }) {
  const [helpOpen, setHelpOpen] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="block text-[10px] font-semibold text-surface-500 uppercase tracking-wider">
          {label} {required && <span className="text-red-400">*</span>}
          {optional && <span className="text-surface-500/60">(opt)</span>}
          {isSet && (
            <span className="ml-1.5 inline-flex items-center gap-1 text-emerald-400 text-[10px] font-semibold uppercase">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Set
            </span>
          )}
        </label>
        <a
          href={providerUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-brand-400 hover:text-brand-300 transition-colors px-2 py-0.5 rounded-lg bg-brand-500/8 hover:bg-brand-500/15"
        >
          Get {providerName} Key <ExternalLink size={10} />
        </a>
      </div>
      <input
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`input-premium w-full mono ${fieldError ? 'border-red-500/50 focus:border-red-500' : ''}`}
      />
      {fieldError && (
        <p className="text-xs text-red-400 mt-1">{fieldError}</p>
      )}
      {/* Expandable help */}
      {helpSteps && (
        <div className="mt-2">
          <button
            onClick={() => setHelpOpen(!helpOpen)}
            className="text-xs text-surface-500 hover:text-surface-700 transition-colors flex items-center gap-1.5"
          >
            <HelpCircle size={11} />
            How to get this key
            {helpOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          </button>
          <AnimatePresence>
            {helpOpen && (
              <motion.ol
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                className="mt-2.5 ml-1 space-y-2 list-decimal list-inside"
              >
                {helpSteps.map((s, i) => (
                  <li key={i} className="text-xs text-surface-600 leading-relaxed">{s}</li>
                ))}
              </motion.ol>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

function KeyStatusRow({ label, active, hint }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[10px] font-semibold text-surface-500 uppercase tracking-wider">{label}</span>
      <span className={`inline-flex items-center gap-2 text-xs font-medium ${active ? 'text-emerald-400' : 'text-surface-500'}`}>
        <motion.span
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-emerald-400' : 'bg-surface-500'}`}
        />
        {active ? `Connected (${hint})` : 'Not set'}
      </span>
    </div>
  );
}

/* ── Video Preferences (Phase 4 & 5) ─────────────────────────── */

const STYLE_DESCRIPTIONS = {
  bold_pop: 'Large bold text with thick outline — maximum visibility',
  minimal: 'Clean thin text with subtle outline — understated elegance',
  cinematic: 'Semi-transparent background box — cinematic movie feel',
  accent_highlight: 'Teal-accented bold text — branded & eye-catching',
};

const SPEED_LABELS = {
  '0.8': 'Slow — Relaxed, cinematic pacing',
  '0.9': 'Slightly slow — Clear & deliberate',
  '1.0': 'Normal — Default narration speed',
  '1.1': 'Slightly fast — Energetic & punchy',
  '1.2': 'Fast — Quick-paced delivery',
};

function VideoPreferencesTab() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [subtitleStyle, setSubtitleStyle] = useState('bold_pop');
  const [burnCaptions, setBurnCaptions] = useState(true);
  const [speechSpeed, setSpeechSpeed] = useState('1.0');
  const [availableStyles, setAvailableStyles] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/api/videos/preferences');
        setSubtitleStyle(data.subtitle_style || 'bold_pop');
        setBurnCaptions(data.burn_captions ?? true);
        setSpeechSpeed(data.speech_speed || '1.0');
        setAvailableStyles(data.available_styles || []);
      } catch (err) {
        setError('Failed to load video preferences.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleSave() {
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      await api.put('/api/videos/preferences', {
        subtitle_style: subtitleStyle,
        burn_captions: burnCaptions,
        speech_speed: speechSpeed === '1.0' ? null : speechSpeed,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save preferences.');
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 max-w-lg">
        <SkeletonLine width="w-40" />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-lg">
      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-[10px] bg-violet-500/10 flex items-center justify-center">
          <Film size={16} className="text-violet-400" />
        </div>
        <div>
          <h3 className="text-[15px] font-semibold text-white">Video Preferences</h3>
          <p className="text-[12px] text-surface-600">Customize subtitle style, captions & speech speed</p>
        </div>
      </div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-red-500/6 text-red-400 text-xs px-3 py-2.5 rounded-lg"
          >
            {error}
          </motion.div>
        )}
        {saved && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-emerald-500/6 text-emerald-400 text-xs px-3 py-2.5 rounded-lg flex items-center gap-2"
          >
            <Check size={16} /> Preferences saved — applied to your next video.
          </motion.div>
        )}
      </AnimatePresence>

      {/* Subtitle Style */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Type size={14} className="text-surface-500" />
          <label className="text-[10px] font-semibold text-surface-500 uppercase tracking-widest">Caption Style</label>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {(availableStyles.length > 0 ? availableStyles : [
            { key: 'bold_pop', name: 'Bold Pop' },
            { key: 'minimal', name: 'Minimal' },
            { key: 'cinematic', name: 'Cinematic' },
            { key: 'accent_highlight', name: 'Accent Highlight' },
          ]).map((style) => (
            <motion.button
              key={style.key}
              onClick={() => setSubtitleStyle(style.key)}
              whileTap={{ scale: 0.98 }}
              className={`relative p-3 rounded-lg text-left transition-all ${
                subtitleStyle === style.key
                  ? 'bg-brand-500/10 ring-1 ring-brand-500/30'
                  : 'bg-surface-100/30 hover:bg-surface-200/50'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className={`text-sm font-semibold ${subtitleStyle === style.key ? 'text-brand-400' : 'text-white'}`}>
                  {style.name}
                </span>
                {subtitleStyle === style.key && (
                  <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }}>
                    <CheckCircle2 size={16} className="text-brand-400" />
                  </motion.div>
                )}
              </div>
              <p className="text-xs text-surface-500 leading-relaxed">
                {STYLE_DESCRIPTIONS[style.key] || `${style.bold ? 'Bold' : 'Regular'} ${style.font_size}px — ${style.border_style}`}
              </p>
            </motion.button>
          ))}
        </div>
      </div>

      {/* Burn Captions Toggle */}
      <div className="card p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded bg-surface-200/50 flex items-center justify-center">
              <Type size={12} className="text-surface-500" />
            </div>
            <div>
              <p className="text-xs font-medium text-white">Burn captions into video</p>
              <p className="text-xs text-surface-500">
                {burnCaptions
                  ? 'Captions permanently embedded — visible on all platforms'
                  : 'SRT file only — upload as closed captions on YouTube'}
              </p>
            </div>
          </div>
          <button
            onClick={() => setBurnCaptions(!burnCaptions)}
            className={`relative w-[44px] h-[24px] rounded-full transition-colors duration-200 ${
              burnCaptions ? 'bg-brand-500' : 'bg-surface-300/50'
            }`}
          >
            <motion.div
              animate={{ x: burnCaptions ? 20 : 2 }}
              transition={{ type: 'tween', duration: 0.15 }}
              className="w-5 h-5 rounded-full bg-white shadow-sm absolute top-[2px]"
            />
          </button>
        </div>
      </div>

      {/* Speech Speed */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Volume2 size={14} className="text-surface-500" />
          <label className="text-[10px] font-semibold text-surface-500 uppercase tracking-widest">Speech Speed</label>
        </div>
        <div className="card p-5 space-y-3">
          <input
            type="range"
            min="0.8"
            max="1.2"
            step="0.1"
            value={speechSpeed}
            onChange={(e) => setSpeechSpeed(e.target.value)}
            className="w-full accent-brand-500 cursor-pointer"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-surface-500">0.8× Slow</span>
            <span className="text-sm font-medium text-brand-400">{speechSpeed}×</span>
            <span className="text-xs text-surface-500">1.2× Fast</span>
          </div>
          <p className="text-xs text-surface-500 text-center">
            {SPEED_LABELS[speechSpeed] || 'Custom speed'}
          </p>
        </div>
      </div>

      {/* Info box */}
      <div className="card p-4 flex items-start gap-3">
        <Sparkles size={14} className="text-violet-400 shrink-0 mt-0.5" />
        <p className="text-[12px] text-surface-600 leading-relaxed">
          <strong className="text-surface-700">How it works:</strong> Audio is automatically polished with
          loudness normalization, silence trimming, and subtle ambient background music with voice-priority
          ducking. An SRT file is generated alongside every video for YouTube closed captions.
        </p>
      </div>

      {/* Save */}
      <motion.button
        onClick={handleSave}
        disabled={saving}
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        className="btn-primary flex items-center gap-2 px-5 py-2 text-xs"
      >
        {saving ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
        {saving ? 'Saving…' : 'Save Preferences'}
      </motion.button>
    </div>
  );
}

/* ── YouTube ─────────────────────────────────────────────────── */
function YouTubeTab() {
  const [loading, setLoading] = useState(true);
  const [connection, setConnection] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    async function fetchStatus() {
      try {
        const { data } = await api.get('/oauth/youtube/status');
        setConnection(data);
      } catch (err) {
        if (err.response?.status === 503) {
          setError('YouTube integration is not configured yet.');
        }
      } finally {
        setLoading(false);
      }
    }
    fetchStatus();
  }, []);

  async function handleConnect() {
    setActionLoading(true);
    setError('');
    try {
      const { data } = await api.get('/oauth/youtube/authorize');
      window.location.href = data.auth_url;
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 503) {
        setError('YouTube integration is not configured yet.');
      } else {
        setError(detail || 'Failed to start YouTube connection.');
      }
      setActionLoading(false);
    }
  }

  async function handleDisconnect() {
    setActionLoading(true);
    setError('');
    try {
      await api.delete('/oauth/youtube/disconnect');
      setConnection({ connected: false });
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to disconnect.');
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 max-w-md">
        <SkeletonLine width="w-40" />
        <SkeletonCard />
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-md">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-[10px] bg-red-500/10 flex items-center justify-center">
          <Youtube size={16} className="text-red-400" />
        </div>
        <div>
          <h3 className="text-[15px] font-semibold text-white">YouTube Connection</h3>
          <p className="text-[12px] text-surface-600">Upload videos directly to your channel</p>
        </div>
      </div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-red-500/6 text-red-400 text-xs px-3 py-2.5 rounded-lg"
          >
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {connection?.connected ? (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="card p-5 space-y-3"
        >
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-[10px] bg-red-500/10 flex items-center justify-center">
              <Youtube size={16} className="text-red-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-[13px] font-semibold text-white truncate">
                {connection.channel_title || 'YouTube Channel'}
              </p>
              <p className="text-[11px] text-surface-500 truncate">
                {connection.provider_email || connection.channel_id}
              </p>
            </div>
            <span className="badge badge-posted flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              Connected
            </span>
          </div>

          {connection.channel_id && (
            <div className="bg-surface-200/40 rounded p-3 space-y-2">
              <Row label="Channel ID" value={connection.channel_id} />
              {connection.connected_at && (
                <Row label="Connected" value={new Date(connection.connected_at).toLocaleDateString()} />
              )}
            </div>
          )}

          <motion.button
            onClick={handleDisconnect}
            disabled={actionLoading}
            whileTap={{ scale: 0.98 }}
            className="w-full px-3 py-2 rounded-lg text-xs font-medium bg-red-500/8 text-red-400 hover:bg-red-500/15 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {actionLoading ? <RefreshCw size={14} className="animate-spin" /> : 'Disconnect YouTube'}
          </motion.button>
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-3 card p-5"
        >
          <div className="w-9 h-9 rounded-[10px] bg-red-500/10 flex items-center justify-center">
            <Youtube size={16} className="text-red-400" />
          </div>
          <div className="flex-1">
            <p className="text-[13px] font-semibold text-white">No channel connected</p>
            <p className="text-[11px] text-surface-500">Authorize via Google OAuth</p>
          </div>
          <motion.button
            onClick={handleConnect}
            disabled={actionLoading}
            whileTap={{ scale: 0.98 }}
            className="px-4 py-2 rounded text-xs font-medium bg-red-500 text-white hover:bg-red-400 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {actionLoading ? <RefreshCw size={14} className="animate-spin" /> : 'Connect'}
          </motion.button>
        </motion.div>
      )}
    </div>
  );
}

/* ── Notifications ───────────────────────────────────────────── */
function NotificationsTab() {
  const [emailNotifs, setEmailNotifs] = useState(true);
  const [failAlerts, setFailAlerts] = useState(true);
  const [weeklyDigest, setWeeklyDigest] = useState(false);

  return (
    <div className="space-y-8 max-w-md">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-[10px] bg-blue-500/10 flex items-center justify-center">
          <Bell size={16} className="text-blue-400" />
        </div>
        <div>
          <h3 className="text-[15px] font-semibold text-white">Notification Preferences</h3>
          <p className="text-[12px] text-surface-600">Choose what you want to be notified about</p>
        </div>
      </div>

      <div className="space-y-2">
        <Toggle label="Email notifications" description="Get notified when videos are posted" checked={emailNotifs} onChange={setEmailNotifs} />
        <Toggle label="Failure alerts" description="Immediately notified if a video fails" checked={failAlerts} onChange={setFailAlerts} />
        <Toggle label="Weekly digest" description="Summary of your channel performance" checked={weeklyDigest} onChange={setWeeklyDigest} />
      </div>
    </div>
  );
}

function Toggle({ label, description, checked, onChange }) {
  return (
    <div className="setting-row flex items-center justify-between py-1">
      <div>
        <p className="text-[13px] font-medium text-white">{label}</p>
        <p className="text-[12px] text-surface-500 mt-1">{description}</p>
      </div>
      <motion.button
        onClick={() => onChange(!checked)}
        whileTap={{ scale: 0.9 }}
        className={`relative w-[44px] h-[24px] rounded-full transition-colors duration-150 shrink-0 ${
          checked ? 'bg-brand-500' : 'bg-surface-400'
        }`}
      >
        <motion.span
          animate={{ x: checked ? 20 : 0 }}
          transition={{ type: 'tween', duration: 0.15 }}
          className="absolute top-[2px] left-[2px] w-5 h-5 bg-white rounded-full shadow-sm"
        />
      </motion.button>
    </div>
  );
}

/* ── Plan ────────────────────────────────────────────────────── */
function PlanTab({ plan }) {
  const [loading, setLoading] = useState(null);
  const [error, setError] = useState('');

  const plans = [
    { key: 'free', name: 'Free', price: '$0', period: '/mo', features: ['1 video/month', 'Basic templates', 'Community support'], color: 'from-surface-400 to-surface-500' },
    { key: 'starter', name: 'Starter', price: '$29', period: '/mo', features: ['10 videos/month', 'All voices', 'Email support', 'Stock footage'], color: 'from-blue-500 to-blue-600' },
    { key: 'pro', name: 'Pro', price: '$79', period: '/mo', features: ['50 videos/month', 'Custom branding', 'Priority support', 'Analytics', 'Auto-scheduling'], color: 'from-brand-500 to-brand-600', popular: true },
    { key: 'agency', name: 'Agency', price: '$199', period: '/mo', features: ['Unlimited videos', 'Multi-channel', 'API access', 'Dedicated manager', 'White label'], color: 'from-amber-500 to-amber-600' },
  ];

  async function handlePlanAction(planKey) {
    setError('');
    if (planKey === 'free') {
      setLoading('free');
      try {
        const { data } = await api.get('/billing/portal');
        window.location.href = data.portal_url;
      } catch (err) {
        const detail = err.response?.data?.detail;
        if (err.response?.status === 503) setError('Billing is not configured yet.');
        else if (err.response?.status === 404) setError('No billing account found.');
        else setError(detail || 'Could not open billing portal.');
      } finally {
        setLoading(null);
      }
      return;
    }

    setLoading(planKey);
    try {
      const { data } = await api.post('/billing/create-checkout-session', { plan: planKey });
      window.location.href = data.checkout_url;
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 503) setError('Billing is not configured yet.');
      else setError(detail || 'Could not start checkout.');
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-[10px] bg-brand-500/10 flex items-center justify-center">
          <CreditCard size={16} className="text-brand-400" />
        </div>
        <div>
          <h3 className="text-[15px] font-semibold text-white">Your Plan</h3>
          <p className="text-[12px] text-surface-600">Upgrade or manage your subscription</p>
        </div>
      </div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-red-500/6 text-red-400 text-xs px-3 py-2.5 rounded-lg"
          >
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {plans.map((p, i) => (
          <motion.div
            key={p.key}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, delay: 0.04 * i, ease }}
            className={`relative rounded-lg p-5 transition-all ${
              plan === p.key
                ? 'bg-brand-500/10 ring-1 ring-brand-500/30'
                : 'bg-surface-200/30 hover:bg-surface-200/50'
            }`}
          >
            {p.popular && (
              <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 text-[9px] font-bold uppercase tracking-widest px-2.5 py-0.5 rounded bg-brand-500 text-white">
                Popular
              </span>
            )}
            <div className={`w-7 h-7 rounded bg-gradient-to-br ${p.color} flex items-center justify-center mb-2`}>
              <CreditCard size={12} className="text-white" />
            </div>
            <p className="text-sm font-semibold text-white">{p.name}</p>
            <p className="mt-1">
              <span className="text-2xl font-bold text-white">{p.price}</span>
              <span className="text-xs text-surface-500">{p.period}</span>
            </p>
            <ul className="mt-5 space-y-3">
              {p.features.map((f) => (
                <li key={f} className="text-xs text-surface-600 flex items-center gap-2">
                  <Check size={12} className="text-brand-400 shrink-0" />
                  {f}
                </li>
              ))}
            </ul>
            {plan === p.key ? (
              <span className="inline-block mt-4 text-xs font-semibold text-brand-400">
                ✓ Current Plan
              </span>
            ) : (
              <motion.button
                onClick={() => handlePlanAction(p.key)}
                disabled={loading !== null}
                whileTap={{ scale: 0.98 }}
                className={`mt-3 w-full px-3 py-2 rounded text-xs font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2 ${
                  p.key === 'free'
                    ? 'bg-surface-300/60 text-surface-700 hover:bg-surface-400/60'
                    : 'btn-primary'
                }`}
              >
                {loading === p.key ? (
                  <RefreshCw size={12} className="animate-spin" />
                ) : p.key === 'free' ? (
                  'Downgrade'
                ) : (
                  'Upgrade'
                )}
              </motion.button>
            )}
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* ── API Usage ───────────────────────────────────────────────── */
function UsageTab() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchStats() {
      try {
        const { data } = await api.get('/api/videos/stats');
        setStats(data);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    }
    fetchStats();
  }, []);

  if (loading) {
    return (
      <div className="space-y-4 max-w-md">
        <SkeletonLine width="w-40" />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  const total = stats?.total_generated || 0;
  const posted = stats?.total_posted || 0;
  const failed = stats?.total_failed || 0;
  const pending = stats?.total_pending || 0;
  const monthlyUsed = stats?.monthly_used || 0;
  const monthlyLimit = stats?.monthly_limit || 1;
  const plan = stats?.plan || 'free';
  const usagePct = Math.min(100, Math.round((monthlyUsed / monthlyLimit) * 100));

  return (
    <div className="space-y-8 max-w-md">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-[10px] bg-emerald-500/10 flex items-center justify-center">
          <BarChart3 size={16} className="text-emerald-400" />
        </div>
        <div>
          <h3 className="text-[15px] font-semibold text-white">Usage & Stats</h3>
          <p className="text-[12px] text-surface-600">Your video generation activity</p>
        </div>
      </div>

      {/* Monthly quota progress */}
      <div className="card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold text-surface-500 uppercase tracking-widest">
            Monthly Quota ({plan.charAt(0).toUpperCase() + plan.slice(1)})
          </span>
          <span className="text-xs text-white font-semibold tabular-nums">
            {monthlyUsed} / {monthlyLimit >= 999_999 ? '∞' : monthlyLimit}
          </span>
        </div>
        <div className="w-full bg-surface-300/40 rounded-full h-[3px] overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${monthlyLimit >= 999_999 ? 5 : usagePct}%` }}
            transition={{ duration: 0.8, delay: 0.15, ease }}
            className={`h-[3px] rounded-full ${
              usagePct >= 90 ? 'bg-red-500' :
              usagePct >= 70 ? 'bg-amber-500' :
              'bg-brand-500'
            }`}
          />
        </div>
        {usagePct >= 90 && monthlyLimit < 999_999 && (
          <p className="text-xs text-amber-400 flex items-center gap-1.5">
            <Zap size={12} /> Approaching limit — consider upgrading your plan.
          </p>
        )}
      </div>

      <div className="card p-5 space-y-3">
        <Row label="Total videos generated" value={String(total)} />
        <div className="h-px bg-white/4" />
        <Row label="Successfully posted" value={String(posted)} />
        <div className="h-px bg-white/4" />
        <Row label="Currently generating" value={String(pending)} />
        <div className="h-px bg-white/4" />
        <Row label="Failed" value={String(failed)} />
      </div>

      <div className="card p-4 flex items-start gap-3">
        <Zap size={16} className="text-amber-400 shrink-0 mt-0.5" />
        <p className="text-[12px] text-surface-600 leading-[1.7]">
          <strong className="text-surface-700">Bring Your Own Keys:</strong> Since you provide your own
          API keys, video generation costs are billed directly to your OpenAI, ElevenLabs, and Pexels
          accounts. A typical video costs roughly $0.05–$0.15 in total API credits.
        </p>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[12px] text-surface-500">{label}</span>
      <span className="text-xs text-white font-medium tabular-nums">{value}</span>
    </div>
  );
}
