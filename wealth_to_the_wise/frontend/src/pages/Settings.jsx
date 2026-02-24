import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import Spinner from '../components/Spinner';
import { Save, Youtube, Bell, CreditCard, BarChart3, Key } from 'lucide-react';

const tabs = [
  { key: 'account', label: 'Account', icon: Save },
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

  // Sync tab when navigating back with ?tab= param (e.g. from OAuth callback)
  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam && tabs.some((t) => t.key === tabParam)) {
      setActiveTab(tabParam);
    }
  }, [searchParams]);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold text-white">Settings</h1>
        <p className="text-sm text-surface-700 mt-1">Manage your account and preferences</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-surface-100 border border-surface-300 rounded-xl p-1 overflow-x-auto scrollbar-none">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-2 px-3 sm:px-4 py-2 rounded-lg text-xs sm:text-sm font-medium transition-all whitespace-nowrap ${
              activeTab === key
                ? 'gradient-brand text-white shadow-md shadow-brand-500/15'
                : 'text-surface-600 hover:text-surface-800 hover:bg-surface-200/50'
            }`}
          >
            <Icon size={16} />
            <span className="hidden sm:inline">{label}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="bg-surface-100 border border-surface-300 rounded-xl p-4 sm:p-6">
        {activeTab === 'account' && (
          <AccountTab fullName={fullName} setFullName={setFullName} email={email} />
        )}
        {activeTab === 'apikeys' && <ApiKeysTab />}
        {activeTab === 'youtube' && <YouTubeTab />}
        {activeTab === 'notifications' && <NotificationsTab />}
        {activeTab === 'plan' && <PlanTab plan={user?.plan || 'free'} />}
        {activeTab === 'usage' && <UsageTab />}
      </div>
    </div>
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
    <div className="space-y-5 max-w-md">
      <h3 className="text-lg font-medium text-white">Account Details</h3>
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-2.5 rounded-lg">
          {error}
        </div>
      )}
      {saved && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm px-4 py-2.5 rounded-lg">
          Changes saved.
        </div>
      )}
      <div>
        <label className="block text-xs font-medium text-surface-700 mb-1.5">Full Name</label>
        <input
          type="text"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="w-full px-3 py-2.5 rounded-lg bg-surface-200 border border-surface-300 text-surface-900 text-sm placeholder-surface-500 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-surface-700 mb-1.5">Email</label>
        <input
          type="email"
          value={email}
          disabled
          className="w-full px-3 py-2.5 rounded-lg bg-surface-200/50 border border-surface-300 text-surface-600 text-sm cursor-not-allowed"
        />
      </div>
      <button
        onClick={handleSave}
        disabled={saving}
        className="px-5 py-2.5 rounded-lg text-sm font-medium gradient-brand text-white hover:opacity-90 transition-all disabled:opacity-50 flex items-center gap-2 glow-brand"
      >
        {saving ? <Spinner className="w-4 h-4" /> : 'Save Changes'}
      </button>
    </div>
  );
}

/* ── API Keys (BYOK) ─────────────────────────────────────────── */
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

  async function handleSave() {
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      // Only send fields that the user has actually typed something into
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
      <div className="flex items-center justify-center py-12">
        <Spinner className="w-6 h-6 text-brand-500" />
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-lg">
      <div>
        <h3 className="text-lg font-medium text-white">Your API Keys</h3>
        <p className="text-sm text-surface-700 mt-1">
          Tubevo uses <strong>your own API keys</strong> to generate videos. Your keys are stored
          securely and never shared. You only pay for what you use directly to each provider.
        </p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-2.5 rounded-lg">
          {error}
        </div>
      )}
      {saved && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm px-4 py-2.5 rounded-lg">
          Keys saved successfully!
        </div>
      )}

      {/* Current status */}
      {keyStatus && (
        <div className="bg-surface-200 border border-surface-300 rounded-xl p-4 space-y-2">
          <p className="text-xs font-medium text-surface-700 mb-2">Current Status</p>
          <KeyStatusRow label="OpenAI" active={keyStatus.has_openai_key} hint={keyStatus.openai_key_hint} />
          <KeyStatusRow label="ElevenLabs" active={keyStatus.has_elevenlabs_key} hint={keyStatus.elevenlabs_key_hint} />
          <KeyStatusRow label="Pexels" active={keyStatus.has_pexels_key} hint={keyStatus.pexels_key_hint} />
          {keyStatus.elevenlabs_voice_id && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-surface-600">Voice ID</span>
              <span className="text-xs text-surface-800 font-mono">{keyStatus.elevenlabs_voice_id}</span>
            </div>
          )}
        </div>
      )}

      {/* Input fields */}
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-surface-700 mb-1.5">
            OpenAI API Key <span className="text-red-400">*</span>
          </label>
          <input
            type="password"
            value={form.openai_api_key}
            onChange={(e) => setForm({ ...form, openai_api_key: e.target.value })}
            placeholder={keyStatus?.has_openai_key ? `Current: ••••${keyStatus.openai_key_hint?.slice(-4) || ''}` : 'sk-...'}
            className="w-full px-3 py-2.5 rounded-lg bg-surface-200 border border-surface-300 text-surface-900 text-sm font-mono placeholder-surface-500 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500"
          />
          <p className="text-xs text-surface-600 mt-1">
            Get yours at{' '}
            <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer" className="text-brand-400 hover:underline">
              platform.openai.com
            </a>
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-surface-700 mb-1.5">
            ElevenLabs API Key <span className="text-red-400">*</span>
          </label>
          <input
            type="password"
            value={form.elevenlabs_api_key}
            onChange={(e) => setForm({ ...form, elevenlabs_api_key: e.target.value })}
            placeholder={keyStatus?.has_elevenlabs_key ? `Current: ••••${keyStatus.elevenlabs_key_hint?.slice(-4) || ''}` : 'sk_...'}
            className="w-full px-3 py-2.5 rounded-lg bg-surface-200 border border-surface-300 text-surface-900 text-sm font-mono placeholder-surface-500 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500"
          />
          <p className="text-xs text-surface-600 mt-1">
            Get yours at{' '}
            <a href="https://elevenlabs.io" target="_blank" rel="noopener noreferrer" className="text-brand-400 hover:underline">
              elevenlabs.io
            </a>
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-surface-700 mb-1.5">
            ElevenLabs Voice ID <span className="text-surface-500">(optional)</span>
          </label>
          <input
            type="text"
            value={form.elevenlabs_voice_id}
            onChange={(e) => setForm({ ...form, elevenlabs_voice_id: e.target.value })}
            placeholder={keyStatus?.elevenlabs_voice_id || 'e.g. pNInz6obpgDQGcFmaJgB'}
            className="w-full px-3 py-2.5 rounded-lg bg-surface-200 border border-surface-300 text-surface-900 text-sm font-mono placeholder-surface-500 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500"
          />
          <p className="text-xs text-surface-600 mt-1">
            Leave blank to use the default voice. Find voice IDs in your ElevenLabs dashboard.
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-surface-700 mb-1.5">
            Pexels API Key <span className="text-surface-500">(optional — for stock footage)</span>
          </label>
          <input
            type="password"
            value={form.pexels_api_key}
            onChange={(e) => setForm({ ...form, pexels_api_key: e.target.value })}
            placeholder={keyStatus?.has_pexels_key ? `Current: ••••${keyStatus.pexels_key_hint?.slice(-4) || ''}` : 'Free at pexels.com/api'}
            className="w-full px-3 py-2.5 rounded-lg bg-surface-200 border border-surface-300 text-surface-900 text-sm font-mono placeholder-surface-500 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500"
          />
          <p className="text-xs text-surface-600 mt-1">
            Free at{' '}
            <a href="https://www.pexels.com/api/" target="_blank" rel="noopener noreferrer" className="text-brand-400 hover:underline">
              pexels.com/api
            </a>
            . Without this, videos use a plain dark background.
          </p>
        </div>
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="px-5 py-2.5 rounded-lg text-sm font-medium gradient-brand text-white hover:opacity-90 transition-all disabled:opacity-50 flex items-center gap-2 glow-brand"
      >
        {saving ? <Spinner className="w-4 h-4" /> : 'Save API Keys'}
      </button>

      <div className="bg-surface-200/50 border border-surface-300 rounded-xl p-4">
        <p className="text-xs text-surface-600">
          <strong className="text-surface-700">Why bring your own keys?</strong> This keeps your costs
          transparent — you pay each provider directly for what you use. No hidden markups.
          A typical video costs ~$0.05 in OpenAI credits and ~$0.10 in ElevenLabs credits.
        </p>
      </div>
    </div>
  );
}

function KeyStatusRow({ label, active, hint }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-surface-600">{label}</span>
      <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${active ? 'text-emerald-400' : 'text-surface-500'}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-emerald-400' : 'bg-surface-500'}`} />
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

  // Fetch current connection status on mount
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
      // Redirect user to Google consent screen
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
      <div className="flex items-center justify-center py-12">
        <Spinner className="w-6 h-6 text-brand-500" />
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-md">
      <h3 className="text-lg font-medium text-white">YouTube Connection</h3>
      <p className="text-sm text-surface-700">
        Connect your YouTube channel to allow Tubevo to upload videos on your behalf.
      </p>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-2.5 rounded-lg">
          {error}
        </div>
      )}

      {connection?.connected ? (
        /* ── Connected state ── */
        <div className="bg-surface-200 border border-emerald-500/20 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-full bg-red-500/15 flex items-center justify-center ring-1 ring-red-500/20">
              <Youtube size={20} className="text-red-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">
                {connection.channel_title || 'YouTube Channel'}
              </p>
              <p className="text-xs text-surface-600 truncate">
                {connection.provider_email || connection.channel_id}
              </p>
            </div>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Connected
            </span>
          </div>

          {connection.channel_id && (
            <div className="bg-surface-100 rounded-lg p-3 space-y-1.5">
              <Row label="Channel ID" value={connection.channel_id} />
              {connection.connected_at && (
                <Row label="Connected" value={new Date(connection.connected_at).toLocaleDateString()} />
              )}
            </div>
          )}

          <button
            onClick={handleDisconnect}
            disabled={actionLoading}
            className="w-full px-4 py-2 rounded-lg text-sm font-medium bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {actionLoading ? <Spinner className="w-4 h-4" /> : 'Disconnect YouTube'}
          </button>
        </div>
      ) : (
        /* ── Disconnected state ── */
        <div className="flex items-center gap-4 bg-surface-200 border border-surface-300 rounded-xl p-4">
          <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center">
            <Youtube size={20} className="text-red-400" />
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-surface-900">No channel connected</p>
            <p className="text-xs text-surface-600">Authorize via Google OAuth</p>
          </div>
          <button
            onClick={handleConnect}
            disabled={actionLoading}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-red-500 text-white hover:bg-red-400 transition-all disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-red-500/20"
          >
            {actionLoading ? <Spinner className="w-3 h-3" /> : 'Connect'}
          </button>
        </div>
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
    <div className="space-y-5 max-w-md">
      <h3 className="text-lg font-medium text-white">Notification Preferences</h3>
      <Toggle label="Email notifications" description="Get notified when videos are posted" checked={emailNotifs} onChange={setEmailNotifs} />
      <Toggle label="Failure alerts" description="Immediately notified if a video fails" checked={failAlerts} onChange={setFailAlerts} />
      <Toggle label="Weekly digest" description="Summary of your channel performance" checked={weeklyDigest} onChange={setWeeklyDigest} />
    </div>
  );
}

function Toggle({ label, description, checked, onChange }) {
  return (
    <div className="flex items-center justify-between py-2">
      <div>
        <p className="text-sm font-medium text-surface-900">{label}</p>
        <p className="text-xs text-surface-600 mt-0.5">{description}</p>
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`relative w-11 h-6 rounded-full transition-all ${
          checked ? 'gradient-brand shadow-md shadow-brand-500/25' : 'bg-surface-400'
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${
            checked ? 'translate-x-5' : 'translate-x-0'
          }`}
        />
      </button>
    </div>
  );
}

/* ── Plan ────────────────────────────────────────────────────── */
function PlanTab({ plan }) {
  const [loading, setLoading] = useState(null); // tracks which plan is loading
  const [error, setError] = useState('');

  const plans = [
    { key: 'free', name: 'Free', price: '$0/mo', features: ['1 video/month', 'Basic templates', 'Community support'] },
    { key: 'starter', name: 'Starter', price: '$29/mo', features: ['10 videos/month', 'All voices', 'Email support', 'Stock footage'] },
    { key: 'pro', name: 'Pro', price: '$79/mo', features: ['50 videos/month', 'Custom branding', 'Priority support', 'Analytics', 'Auto-scheduling'] },
    { key: 'agency', name: 'Agency', price: '$199/mo', features: ['Unlimited videos', 'Multi-channel', 'API access', 'Dedicated manager', 'White label'] },
  ];

  async function handlePlanAction(planKey) {
    setError('');

    // For downgrades to free, open the billing portal to cancel
    if (planKey === 'free') {
      setLoading('free');
      try {
        const { data } = await api.get('/billing/portal');
        window.location.href = data.portal_url;
      } catch (err) {
        const detail = err.response?.data?.detail;
        if (err.response?.status === 503) {
          setError('Billing is not configured yet.');
        } else if (err.response?.status === 404) {
          setError('No billing account found. Nothing to cancel.');
        } else {
          setError(detail || 'Could not open billing portal.');
        }
      } finally {
        setLoading(null);
      }
      return;
    }

    // For upgrades, create a checkout session
    setLoading(planKey);
    try {
      const { data } = await api.post('/billing/create-checkout-session', { plan: planKey });
      window.location.href = data.checkout_url;
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 503) {
        setError('Billing is not configured yet.');
      } else {
        setError(detail || 'Could not start checkout.');
      }
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="space-y-5">
      <h3 className="text-lg font-medium text-white">Your Plan</h3>
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-2.5 rounded-lg">
          {error}
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {plans.map((p) => (
          <div
            key={p.key}
            className={`rounded-xl border p-5 transition-all ${
              plan === p.key
                ? 'border-brand-500 bg-brand-600/10 glow-brand'
                : 'border-surface-300 bg-surface-200/50 hover:border-surface-400'
            }`}
          >
            <p className="text-sm font-semibold text-white">{p.name}</p>
            <p className="text-2xl font-bold text-white mt-1">{p.price}</p>
            <ul className="mt-4 space-y-2">
              {p.features.map((f) => (
                <li key={f} className="text-xs text-surface-700 flex items-center gap-2">
                  <span className="w-1 h-1 rounded-full bg-brand-400" />
                  {f}
                </li>
              ))}
            </ul>
            {plan === p.key ? (
              <span className="inline-block mt-4 text-xs font-medium text-gradient">
                Current Plan
              </span>
            ) : (
              <button
                onClick={() => handlePlanAction(p.key)}
                disabled={loading !== null}
                className={`mt-4 w-full px-3 py-2 rounded-lg text-xs font-medium transition-all disabled:opacity-50 flex items-center justify-center gap-2 ${
                  p.key === 'free'
                    ? 'bg-surface-300 text-surface-800 hover:bg-surface-400'
                    : 'gradient-brand text-white hover:opacity-90 glow-brand'
                }`}
              >
                {loading === p.key ? (
                  <Spinner className="w-3 h-3" />
                ) : p.key === 'free' ? (
                  'Downgrade'
                ) : (
                  'Upgrade'
                )}
              </button>
            )}
          </div>
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
      <div className="flex items-center justify-center py-12">
        <Spinner className="w-6 h-6 text-brand-500" />
      </div>
    );
  }

  const total = stats?.total_generated || 0;
  const posted = stats?.total_posted || 0;
  const failed = stats?.total_failed || 0;
  const pending = stats?.total_pending || 0;

  return (
    <div className="space-y-5 max-w-md">
      <h3 className="text-lg font-medium text-white">Usage & Stats</h3>
      <p className="text-sm text-surface-700">
        Your video generation activity. With BYOK, API costs are billed directly by each provider.
      </p>

      <div className="bg-surface-200 border border-surface-300 rounded-xl p-4 space-y-2">
        <Row label="Total videos generated" value={String(total)} />
        <Row label="Successfully posted" value={String(posted)} />
        <Row label="Currently generating" value={String(pending)} />
        <Row label="Failed" value={String(failed)} />
      </div>

      <div className="bg-surface-200/50 border border-surface-300 rounded-xl p-4">
        <p className="text-xs text-surface-600">
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
      <span className="text-xs text-surface-600">{label}</span>
      <span className="text-xs text-surface-800 font-medium">{value}</span>
    </div>
  );
}
