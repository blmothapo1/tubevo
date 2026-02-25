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
} from 'lucide-react';
import useOnboarding from '../hooks/useOnboarding';

const ease = [0.25, 0.1, 0.25, 1];

const tabs = [
  { key: 'account', label: 'Account', icon: User },
  { key: 'apikeys', label: 'API Keys', icon: Key },
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
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Settings</h1>
        <p className="text-sm text-surface-600 mt-2">Manage your account and preferences</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 card p-1.5 overflow-x-auto scrollbar-none">
        {tabs.map(({ key, label, icon: Icon }) => (
          <motion.button
            key={key}
            onClick={() => setActiveTab(key)}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            {...(key === 'apikeys' ? { 'data-tour': 'settings-apikeys-tab' } : {})}
            className={`relative flex items-center gap-2 px-3 sm:px-4 py-2.5 rounded-lg text-xs sm:text-sm font-medium transition-all whitespace-nowrap ${
              activeTab === key
                ? 'text-white'
                : 'text-surface-600 hover:text-surface-800 hover:bg-surface-200/40'
            }`}
          >
            {activeTab === key && (
              <motion.div
                layoutId="settings-tab-bg"
                className="absolute inset-0 bg-gradient-to-r from-brand-500 to-brand-600 rounded-lg shadow-md shadow-brand-500/20"
                transition={{ type: 'spring', bounce: 0.18, duration: 0.5 }}
              />
            )}
            <span className="relative z-10 flex items-center gap-2">
              <Icon size={16} />
              <span className="hidden sm:inline">{label}</span>
            </span>
          </motion.button>
        ))}
      </div>

      {/* Tab Content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.3, ease }}
          className="card-elevated p-5 sm:p-8"
        >
          {activeTab === 'account' && (
            <AccountTab fullName={fullName} setFullName={setFullName} email={email} />
          )}
          {activeTab === 'apikeys' && <ApiKeysTab />}
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
    <div className="space-y-6 max-w-md">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500/20 to-brand-600/10 flex items-center justify-center">
          <User size={20} className="text-brand-400" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white">Account Details</h3>
          <p className="text-xs text-surface-600">Update your profile information</p>
        </div>
      </div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-red-500/8 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-xl"
          >
            {error}
          </motion.div>
        )}
        {saved && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-emerald-500/8 border border-emerald-500/20 text-emerald-400 text-sm px-4 py-3 rounded-xl flex items-center gap-2"
          >
            <Check size={16} /> Changes saved successfully.
          </motion.div>
        )}
      </AnimatePresence>

      <div>
        <label className="block text-xs font-medium text-surface-500 mb-2">Full Name</label>
        <input
          type="text"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="input-premium w-full"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-surface-500 mb-2">Email</label>
        <input
          type="email"
          value={email}
          disabled
          className="input-premium w-full opacity-50 cursor-not-allowed"
        />
        <p className="text-xs text-surface-500 mt-1.5">Email cannot be changed.</p>
      </div>
      <motion.button
        onClick={handleSave}
        disabled={saving}
        whileHover={{ scale: 1.02, y: -1 }}
        whileTap={{ scale: 0.97 }}
        className="btn-primary flex items-center gap-2 px-6 py-2.5"
      >
        {saving ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
        {saving ? 'Saving…' : 'Save Changes'}
      </motion.button>

      {/* Replay Tutorial — additive section */}
      <ReplayTutorialSection />
    </div>
  );
}

/* ── Replay Tutorial ──────────────────────────────────────────── */
function ReplayTutorialSection() {
  const { replayTutorial } = useOnboarding();

  return (
    <div className="pt-6 mt-6 border-t border-surface-300/30">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500/20 to-brand-600/10 flex items-center justify-center">
          <PlayCircle size={20} className="text-brand-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">Guided Tutorial</h3>
          <p className="text-xs text-surface-600">Walk through the app features step by step</p>
        </div>
      </div>
      <motion.button
        onClick={replayTutorial}
        whileHover={{ scale: 1.02, y: -1 }}
        whileTap={{ scale: 0.97 }}
        className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium text-brand-400 bg-brand-500/10 border border-brand-500/20 hover:bg-brand-500/20 transition-all"
      >
        <PlayCircle size={16} />
        Replay Tutorial
      </motion.button>
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
    <div className="space-y-6 max-w-xl">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500/20 to-amber-600/10 flex items-center justify-center">
          <Key size={20} className="text-amber-400" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white">Your API Keys</h3>
          <p className="text-xs text-surface-600">
            An API key is a private password that lets Tubevo use AI services on your behalf.
          </p>
        </div>
      </div>

      {/* Setup checklist */}
      <div className="card p-5 space-y-3">
        <p className="text-xs font-medium text-surface-500 uppercase tracking-wider mb-1">Setup Checklist</p>
        {steps.map((s, i) => (
          <div key={i} className="flex items-center gap-3">
            {s.done ? (
              <CheckCircle2 size={18} className="text-emerald-400 shrink-0" />
            ) : (
              <CircleDot size={18} className="text-surface-500 shrink-0" />
            )}
            <span className={`text-sm ${s.done ? 'text-emerald-400 line-through' : 'text-white'}`}>
              {s.label}
              {s.optional && <span className="text-surface-500 text-xs ml-1.5">(optional — free stock footage)</span>}
            </span>
          </div>
        ))}
        {allKeysSet && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="pt-2"
          >
            <a
              href="/videos"
              className="btn-primary inline-flex items-center gap-2 px-5 py-2.5 text-sm w-full justify-center"
            >
              <Sparkles size={16} /> Start Creating Videos <ArrowRight size={14} />
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
            className="bg-red-500/8 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-xl"
          >
            {error}
          </motion.div>
        )}
        {saved && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-emerald-500/8 border border-emerald-500/20 text-emerald-400 text-sm px-4 py-3 rounded-xl flex items-center gap-2"
          >
            <Check size={16} /> Keys saved and encrypted securely.
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input fields with "Get Key" buttons */}
      <div className="space-y-5">
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
            className="input-premium w-full font-mono text-xs"
          />
          <p className="text-xs text-surface-500 mt-1.5">Leave blank to use the default voice.</p>
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
        whileHover={{ scale: 1.02, y: -1 }}
        whileTap={{ scale: 0.97 }}
        className="btn-primary flex items-center gap-2 px-6 py-2.5 w-full justify-center"
      >
        {saving ? <RefreshCw size={16} className="animate-spin" /> : <Shield size={16} />}
        {saving ? 'Encrypting & saving…' : 'Save API Keys'}
      </motion.button>

      <div className="card p-4 flex items-start gap-3">
        <Shield size={16} className="text-brand-400 shrink-0 mt-0.5" />
        <p className="text-xs text-surface-600 leading-relaxed">
          <strong className="text-surface-700">Your keys are encrypted</strong> and stored securely on our servers.
          They are only used to generate videos on your behalf. We never share or expose your keys.
          You pay each provider directly — no hidden markups.
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
        <label className="block text-xs font-medium text-surface-500">
          {label} {required && <span className="text-red-400">*</span>}
          {optional && <span className="text-surface-500/60">(optional)</span>}
          {isSet && (
            <span className="ml-2 inline-flex items-center gap-1 text-emerald-400 text-[10px] font-semibold uppercase">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Connected
            </span>
          )}
        </label>
        <a
          href={providerUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[11px] font-medium text-brand-400 hover:text-brand-300 transition-colors px-2.5 py-1 rounded-lg bg-brand-500/8 hover:bg-brand-500/15 border border-brand-500/15"
        >
          Get {providerName} Key <ExternalLink size={10} />
        </a>
      </div>
      <input
        type="password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`input-premium w-full font-mono text-xs ${fieldError ? 'border-red-500/50 focus:border-red-500' : ''}`}
      />
      {fieldError && (
        <p className="text-xs text-red-400 mt-1">{fieldError}</p>
      )}
      {/* Expandable help */}
      {helpSteps && (
        <div className="mt-1.5">
          <button
            onClick={() => setHelpOpen(!helpOpen)}
            className="text-xs text-surface-500 hover:text-surface-700 transition-colors flex items-center gap-1"
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
                className="mt-2 ml-1 space-y-1.5 list-decimal list-inside"
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
      <span className="text-xs text-surface-500">{label}</span>
      <span className={`inline-flex items-center gap-2 text-xs font-medium ${active ? 'text-emerald-400' : 'text-surface-500'}`}>
        <motion.span
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className={`w-2 h-2 rounded-full ${active ? 'bg-emerald-400 shadow-sm shadow-emerald-400/40' : 'bg-surface-500'}`}
        />
        {active ? `Connected (${hint})` : 'Not set'}
      </span>
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
    <div className="space-y-6 max-w-md">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center ring-1 ring-red-500/20">
          <Youtube size={20} className="text-red-400" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white">YouTube Connection</h3>
          <p className="text-xs text-surface-600">Upload videos directly to your channel</p>
        </div>
      </div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-red-500/8 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-xl"
          >
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {connection?.connected ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="card border-emerald-500/15 p-5 space-y-4"
        >
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-red-500/10 flex items-center justify-center ring-1 ring-red-500/20">
              <Youtube size={24} className="text-red-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white truncate">
                {connection.channel_title || 'YouTube Channel'}
              </p>
              <p className="text-xs text-surface-500 truncate">
                {connection.provider_email || connection.channel_id}
              </p>
            </div>
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Connected
            </span>
          </div>

          {connection.channel_id && (
            <div className="bg-surface-200/40 rounded-xl p-4 space-y-2">
              <Row label="Channel ID" value={connection.channel_id} />
              {connection.connected_at && (
                <Row label="Connected" value={new Date(connection.connected_at).toLocaleDateString()} />
              )}
            </div>
          )}

          <motion.button
            onClick={handleDisconnect}
            disabled={actionLoading}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            className="w-full px-4 py-2.5 rounded-xl text-sm font-medium bg-red-500/8 text-red-400 border border-red-500/20 hover:bg-red-500/15 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {actionLoading ? <RefreshCw size={14} className="animate-spin" /> : 'Disconnect YouTube'}
          </motion.button>
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-4 card p-5"
        >
          <div className="w-12 h-12 rounded-xl bg-red-500/10 flex items-center justify-center">
            <Youtube size={24} className="text-red-400" />
          </div>
          <div className="flex-1">
            <p className="text-sm font-semibold text-white">No channel connected</p>
            <p className="text-xs text-surface-500">Authorize via Google OAuth</p>
          </div>
          <motion.button
            onClick={handleConnect}
            disabled={actionLoading}
            whileHover={{ scale: 1.03, y: -1 }}
            whileTap={{ scale: 0.97 }}
            className="px-5 py-2.5 rounded-xl text-sm font-medium bg-red-500 text-white hover:bg-red-400 transition-all disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-red-500/20"
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
    <div className="space-y-6 max-w-md">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500/20 to-blue-600/10 flex items-center justify-center">
          <Bell size={20} className="text-blue-400" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white">Notification Preferences</h3>
          <p className="text-xs text-surface-600">Choose what you want to be notified about</p>
        </div>
      </div>

      <div className="space-y-1">
        <Toggle label="Email notifications" description="Get notified when videos are posted" checked={emailNotifs} onChange={setEmailNotifs} />
        <Toggle label="Failure alerts" description="Immediately notified if a video fails" checked={failAlerts} onChange={setFailAlerts} />
        <Toggle label="Weekly digest" description="Summary of your channel performance" checked={weeklyDigest} onChange={setWeeklyDigest} />
      </div>
    </div>
  );
}

function Toggle({ label, description, checked, onChange }) {
  return (
    <div className="flex items-center justify-between py-4 border-b border-surface-300/20 last:border-0">
      <div>
        <p className="text-sm font-medium text-white">{label}</p>
        <p className="text-xs text-surface-500 mt-0.5">{description}</p>
      </div>
      <motion.button
        onClick={() => onChange(!checked)}
        whileTap={{ scale: 0.9 }}
        className={`relative w-12 h-7 rounded-full transition-all ${
          checked ? 'bg-gradient-to-r from-brand-500 to-brand-600 shadow-md shadow-brand-500/25' : 'bg-surface-400'
        }`}
      >
        <motion.span
          animate={{ x: checked ? 20 : 0 }}
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          className="absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow-sm"
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
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500/20 to-brand-600/10 flex items-center justify-center">
          <CreditCard size={20} className="text-brand-400" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white">Your Plan</h3>
          <p className="text-xs text-surface-600">Upgrade or manage your subscription</p>
        </div>
      </div>

      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-red-500/8 border border-red-500/20 text-red-400 text-sm px-4 py-3 rounded-xl"
          >
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {plans.map((p, i) => (
          <motion.div
            key={p.key}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.05 * i, ease }}
            whileHover={{ y: -3, scale: 1.01 }}
            className={`relative rounded-2xl border p-5 transition-all ${
              plan === p.key
                ? 'border-brand-500/50 bg-brand-600/8 shadow-lg shadow-brand-500/10'
                : 'border-surface-300/40 bg-surface-200/30 hover:border-surface-400/60'
            }`}
          >
            {p.popular && (
              <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 text-[10px] font-bold uppercase tracking-wider px-3 py-0.5 rounded-full bg-gradient-to-r from-brand-500 to-brand-600 text-white shadow-md shadow-brand-500/20">
                Popular
              </span>
            )}
            <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${p.color} flex items-center justify-center mb-3 shadow-sm`}>
              <CreditCard size={14} className="text-white" />
            </div>
            <p className="text-sm font-semibold text-white">{p.name}</p>
            <p className="mt-1">
              <span className="text-2xl font-bold text-white">{p.price}</span>
              <span className="text-xs text-surface-500">{p.period}</span>
            </p>
            <ul className="mt-4 space-y-2">
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
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                className={`mt-4 w-full px-3 py-2.5 rounded-xl text-xs font-medium transition-all disabled:opacity-50 flex items-center justify-center gap-2 ${
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
    <div className="space-y-6 max-w-md">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500/20 to-emerald-600/10 flex items-center justify-center">
          <BarChart3 size={20} className="text-emerald-400" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white">Usage & Stats</h3>
          <p className="text-xs text-surface-600">Your video generation activity</p>
        </div>
      </div>

      {/* Monthly quota progress */}
      <div className="card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-surface-500 uppercase tracking-wider">
            Monthly Quota ({plan.charAt(0).toUpperCase() + plan.slice(1)})
          </span>
          <span className="text-sm text-white font-semibold">
            {monthlyUsed} / {monthlyLimit >= 999_999 ? '∞' : monthlyLimit}
          </span>
        </div>
        <div className="w-full bg-surface-300/40 rounded-full h-2.5 overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${monthlyLimit >= 999_999 ? 5 : usagePct}%` }}
            transition={{ duration: 1, delay: 0.2, ease }}
            className={`h-2.5 rounded-full ${
              usagePct >= 90 ? 'bg-gradient-to-r from-red-500 to-red-400' :
              usagePct >= 70 ? 'bg-gradient-to-r from-amber-500 to-amber-400' :
              'bg-gradient-to-r from-brand-500 to-brand-400'
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
        <div className="h-px bg-surface-300/20" />
        <Row label="Successfully posted" value={String(posted)} />
        <div className="h-px bg-surface-300/20" />
        <Row label="Currently generating" value={String(pending)} />
        <div className="h-px bg-surface-300/20" />
        <Row label="Failed" value={String(failed)} />
      </div>

      <div className="card p-4 flex items-start gap-3">
        <Zap size={16} className="text-amber-400 shrink-0 mt-0.5" />
        <p className="text-xs text-surface-600 leading-relaxed">
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
    <div className="flex items-center justify-between">
      <span className="text-xs text-surface-500">{label}</span>
      <span className="text-sm text-white font-medium">{value}</span>
    </div>
  );
}
