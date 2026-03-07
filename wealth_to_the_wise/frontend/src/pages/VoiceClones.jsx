import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import { StaggerContainer, StaggerItem } from '../components/Motion';
import { SkeletonStatCards } from '../components/Skeleton';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import {
  Mic, Plus, Trash2, X, RefreshCw, CheckCircle2, Clock, AlertTriangle, Loader2,
  Square, Upload, Play, Pause, CircleDot, ChevronRight,
} from 'lucide-react';

const STATUS_STYLES = {
  pending:    { icon: Clock,         color: 'text-amber-400',   bg: 'bg-amber-500/15',   label: 'Pending' },
  processing: { icon: Loader2,       color: 'text-blue-400',    bg: 'bg-blue-500/15',    label: 'Processing' },
  ready:      { icon: CheckCircle2,  color: 'text-emerald-400', bg: 'bg-emerald-500/15', label: 'Ready' },
  failed:     { icon: AlertTriangle, color: 'text-red-400',     bg: 'bg-red-500/15',     label: 'Failed' },
};

/* ── Waveform visualiser (live mic + playback) ───────────────────── */
function Waveform({ analyser, barCount = 40 }) {
  const canvasRef = useRef(null);
  const rafRef = useRef(null);

  useEffect(() => {
    if (!analyser || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      rafRef.current = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(dataArray);
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const step = Math.floor(bufferLength / barCount);
      const barW = canvas.width / barCount;
      const halfH = canvas.height / 2;

      for (let i = 0; i < barCount; i++) {
        const v = dataArray[i * step] / 255;
        const h = Math.max(2, v * halfH);
        const x = i * barW + barW * 0.15;
        const w = barW * 0.7;
        ctx.fillStyle = `rgba(99,102,241,${0.35 + v * 0.65})`;
        ctx.beginPath();
        ctx.roundRect(x, halfH - h, w, h * 2, 2);
        ctx.fill();
      }
    };
    draw();
    return () => cancelAnimationFrame(rafRef.current);
  }, [analyser, barCount]);

  return (
    <canvas
      ref={canvasRef}
      width={320}
      height={80}
      className="w-full h-[80px] rounded-xl bg-surface-100/50"
    />
  );
}

/* ── Timer display ───────────────────────────────────────────────── */
function Timer({ seconds }) {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');
  return <span className="font-mono text-[24px] text-white tabular-nums">{m}:{s}</span>;
}

/* ── Create Voice Modal with recording ───────────────────────────── */
function CreateVoiceModal({ onClose, onCreated }) {
  // Steps: 'details' → 'record' → 'review' → 'uploading'
  const [step, setStep] = useState('details');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');

  // Recording state
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [playing, setPlaying] = useState(false);

  // Refs
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const audioElRef = useRef(null);
  const playbackAnalyserRef = useRef(null);
  const playbackCtxRef = useRef(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach(t => t.stop());
      audioCtxRef.current?.close().catch(() => {});
      playbackCtxRef.current?.close().catch(() => {});
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  /* ── Start recording ──────────────────────────────────────────── */
  const startRecording = async () => {
    setError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 44100 },
      });
      streamRef.current = stream;

      // Audio context for live waveform
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      audioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      // MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';
      const mr = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mr;
      chunksRef.current = [];

      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        setAudioBlob(blob);
        const url = URL.createObjectURL(blob);
        setAudioUrl(url);
        streamRef.current?.getTracks().forEach(t => t.stop());
        setStep('review');
      };

      mr.start(250);
      setRecording(true);
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed(prev => prev + 1), 1000);
    } catch {
      setError('Microphone access denied. Please allow microphone access and try again.');
    }
  };

  /* ── Stop recording ───────────────────────────────────────────── */
  const stopRecording = () => {
    clearInterval(timerRef.current);
    setRecording(false);
    mediaRecorderRef.current?.stop();
    audioCtxRef.current?.close().catch(() => {});
    analyserRef.current = null;
  };

  /* ── Re-record ────────────────────────────────────────────────── */
  const reRecord = () => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    audioElRef.current?.pause();
    audioElRef.current = null;
    playbackCtxRef.current?.close().catch(() => {});
    playbackAnalyserRef.current = null;
    setAudioBlob(null);
    setAudioUrl(null);
    setElapsed(0);
    setPlaying(false);
    setStep('record');
  };

  /* ── Playback ─────────────────────────────────────────────────── */
  const togglePlay = () => {
    if (!audioElRef.current) {
      const audio = new Audio(audioUrl);
      audioElRef.current = audio;

      // Playback analyser for waveform
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      playbackCtxRef.current = ctx;
      const src = ctx.createMediaElementSource(audio);
      const an = ctx.createAnalyser();
      an.fftSize = 256;
      src.connect(an);
      an.connect(ctx.destination);
      playbackAnalyserRef.current = an;

      audio.onended = () => setPlaying(false);
    }
    if (playing) {
      audioElRef.current.pause();
      setPlaying(false);
    } else {
      audioElRef.current.play();
      setPlaying(true);
    }
  };

  /* ── Upload & create clone ────────────────────────────────────── */
  const submit = async () => {
    if (!audioBlob || !name.trim()) return;
    setError('');
    setStep('uploading');

    try {
      // Step 1: Upload audio sample
      const formData = new FormData();
      formData.append('file', audioBlob, 'voice_sample.webm');
      const uploadRes = await api.post('/voice-clones/upload-sample', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const { file_key, duration_secs } = uploadRes.data;

      // Step 2: Create the voice clone record (worker picks it up)
      await api.post('/voice-clones', {
        name: name.trim(),
        description: description.trim() || null,
        sample_file_key: file_key,
        sample_duration_secs: duration_secs,
      });

      onCreated();
      onClose();
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Failed to create voice clone. Please try again.';
      setError(msg);
      setStep('review');
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="card !rounded-[20px] p-6 w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-white font-semibold text-[15px]">
            {step === 'details' && 'New Voice Clone'}
            {step === 'record' && 'Record Voice Sample'}
            {step === 'review' && 'Review Recording'}
            {step === 'uploading' && 'Creating Voice Clone…'}
          </h2>
          {step !== 'uploading' && (
            <button onClick={onClose} className="text-surface-600 hover:text-white transition-colors">
              <X size={18} />
            </button>
          )}
        </div>

        {/* Error banner */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
              className="bg-red-500/10 border border-red-500/20 text-red-400 text-[12px] px-3 py-2 rounded-lg mb-4 overflow-hidden"
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Step: Details ──────────────────────────────────────── */}
        {step === 'details' && (
          <div className="space-y-3">
            <input
              value={name} onChange={(e) => setName(e.target.value)}
              placeholder="Voice name (e.g., Professional Male)"
              className="input-field"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && name.trim() && setStep('record')}
            />
            <textarea
              value={description} onChange={(e) => setDescription(e.target.value)}
              placeholder="Description (optional)"
              rows={2}
              className="input-field !resize-none"
            />
            <p className="text-surface-600 text-[11px] leading-relaxed">
              You'll record a 30-second+ voice sample in the next step.
              Speak naturally in a quiet environment for the best clone quality.
            </p>
            <div className="flex gap-3 mt-4">
              <button onClick={onClose} className="btn-secondary flex-1 text-[13px]">Cancel</button>
              <button
                onClick={() => setStep('record')}
                disabled={!name.trim()}
                className="btn-primary flex-1 text-[13px] flex items-center justify-center gap-2 disabled:opacity-50"
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}

        {/* ── Step: Record ──────────────────────────────────────── */}
        {step === 'record' && (
          <div className="space-y-4">
            {/* Waveform */}
            <Waveform analyser={analyserRef.current} />

            {/* Timer */}
            <div className="text-center">
              <Timer seconds={elapsed} />
              {recording && elapsed < 30 && (
                <p className="text-amber-400 text-[11px] mt-1">
                  Record at least 30 seconds for best quality
                </p>
              )}
              {recording && elapsed >= 30 && (
                <p className="text-emerald-400 text-[11px] mt-1">
                  ✓ Great length — stop whenever you're ready
                </p>
              )}
            </div>

            {/* Prompt text */}
            {!recording && elapsed === 0 && (
              <div className="bg-surface-100/50 rounded-xl p-4">
                <p className="text-surface-600 text-[12px] leading-relaxed">
                  <strong className="text-surface-500">Read this aloud:</strong>{' '}
                  "The quick brown fox jumps over the lazy dog. Every morning I wake up and plan
                  my day ahead, thinking about what matters most. Financial freedom isn't just about
                  money — it's about having the power to live life on your own terms. Let me show
                  you how compound interest can transform your future, one step at a time."
                </p>
              </div>
            )}

            {/* Controls */}
            <div className="flex justify-center gap-4">
              {!recording ? (
                <button
                  onClick={startRecording}
                  className="w-16 h-16 rounded-full bg-red-500 hover:bg-red-400 flex items-center justify-center transition-all hover:scale-105 active:scale-95 shadow-lg shadow-red-500/25"
                >
                  <CircleDot size={28} className="text-white" />
                </button>
              ) : (
                <button
                  onClick={stopRecording}
                  className="w-16 h-16 rounded-full bg-red-500 hover:bg-red-400 flex items-center justify-center transition-all hover:scale-105 active:scale-95 shadow-lg shadow-red-500/25 animate-pulse"
                >
                  <Square size={22} className="text-white" />
                </button>
              )}
            </div>

            {!recording && elapsed === 0 && (
              <button onClick={() => setStep('details')} className="w-full text-center text-surface-600 text-[12px] hover:text-white transition-colors">
                ← Back to details
              </button>
            )}
          </div>
        )}

        {/* ── Step: Review ──────────────────────────────────────── */}
        {step === 'review' && (
          <div className="space-y-4">
            {/* Playback waveform */}
            <Waveform analyser={playbackAnalyserRef.current} />

            {/* Playback controls + duration */}
            <div className="flex items-center justify-center gap-4">
              <button
                onClick={togglePlay}
                className="w-12 h-12 rounded-full bg-brand-600 hover:bg-brand-500 flex items-center justify-center transition-all hover:scale-105 active:scale-95"
              >
                {playing
                  ? <Pause size={20} className="text-white" />
                  : <Play size={20} className="text-white ml-0.5" />}
              </button>
              <div className="text-center">
                <Timer seconds={elapsed} />
                <p className="text-surface-600 text-[11px]">
                  {audioBlob ? `${(audioBlob.size / 1024).toFixed(0)} KB` : ''}
                </p>
              </div>
            </div>

            {elapsed < 10 && (
              <p className="text-amber-400 text-[11px] text-center bg-amber-500/10 px-3 py-2 rounded-lg">
                ⚠ Very short recording. ElevenLabs recommends at least 30 seconds for good quality.
              </p>
            )}

            {/* Actions */}
            <div className="flex gap-3">
              <button onClick={reRecord} className="btn-secondary flex-1 text-[13px] flex items-center justify-center gap-2">
                <Mic size={14} /> Re-record
              </button>
              <button
                onClick={submit}
                className="btn-primary flex-1 text-[13px] flex items-center justify-center gap-2"
              >
                <Upload size={14} /> Create Clone
              </button>
            </div>
          </div>
        )}

        {/* ── Step: Uploading ───────────────────────────────────── */}
        {step === 'uploading' && (
          <div className="flex flex-col items-center gap-4 py-6">
            <Loader2 size={36} className="text-brand-400 animate-spin" />
            <div className="text-center">
              <p className="text-white text-[14px] font-medium">Uploading voice sample…</p>
              <p className="text-surface-600 text-[12px] mt-1">
                ElevenLabs will process your voice in the background.
              </p>
            </div>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}

/* ── Main page ───────────────────────────────────────────────────── */
export default function VoiceClones() {
  const [clones, setClones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  const fetchClones = useCallback(async () => {
    try {
      const res = await api.get('/voice-clones');
      setClones(res.data.voice_clones || []);
    } catch { /* empty */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchClones(); }, [fetchClones]);

  // Auto-refresh while any clone is pending/processing
  useEffect(() => {
    const hasPending = clones.some(c => c.status === 'pending' || c.status === 'processing');
    if (!hasPending) return;
    const interval = setInterval(fetchClones, 8000);
    return () => clearInterval(interval);
  }, [clones, fetchClones]);

  const deleteClone = async (id) => {
    if (!confirm('Delete this voice clone?')) return;
    try {
      await api.delete(`/voice-clones/${id}`);
      fetchClones();
    } catch { /* empty */ }
  };

  const retryClone = async (id) => {
    try {
      await api.post(`/voice-clones/${id}/retry`);
      fetchClones();
    } catch { /* empty */ }
  };

  if (loading) return <div className="max-w-4xl mx-auto"><SkeletonStatCards /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <PageHeader
        title="Voice Clones"
        subtitle="Create and manage custom voices for your videos"
        action={
          <button onClick={() => setShowCreate(true)}
            className="btn-primary flex items-center gap-2 text-[13px]">
            <Plus size={16} /> New Voice
          </button>
        }
      />

      {/* Create modal */}
      <AnimatePresence>
        {showCreate && (
          <CreateVoiceModal
            onClose={() => setShowCreate(false)}
            onCreated={fetchClones}
          />
        )}
      </AnimatePresence>

      {/* Clone list */}
      {clones.length === 0 ? (
        <EmptyState icon={Mic} title="No voice clones yet"
          description="Record a voice sample and create your first custom voice."
          action={
            <button onClick={() => setShowCreate(true)} className="btn-primary text-[13px] flex items-center gap-2">
              <Mic size={14} /> New Voice
            </button>
          } />
      ) : (
        <StaggerContainer className="space-y-3">
          {clones.map((clone) => {
            const style = STATUS_STYLES[clone.status] || STATUS_STYLES.pending;
            const StatusIcon = style.icon;
            return (
              <StaggerItem key={clone.id}>
                <div className="card p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${style.bg}`}>
                        <StatusIcon size={18} className={`${style.color} ${clone.status === 'processing' ? 'animate-spin' : ''}`} />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-white text-[14px] font-medium">{clone.name}</span>
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${style.bg} ${style.color}`}>{style.label}</span>
                        </div>
                        {clone.description && (
                          <p className="text-surface-600 text-[12px] mt-0.5 max-w-md">{clone.description}</p>
                        )}
                        <div className="flex items-center gap-3 mt-1.5">
                          {clone.elevenlabs_voice_id && (
                            <span className="text-surface-600 text-[11px]">EL: {clone.elevenlabs_voice_id.slice(0, 12)}…</span>
                          )}
                          {clone.sample_duration_secs && (
                            <span className="text-surface-600 text-[11px]">{clone.sample_duration_secs}s sample</span>
                          )}
                          <span className="text-surface-600 text-[11px]">
                            {new Date(clone.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        {clone.error_message && (
                          <p className="text-red-400 text-[12px] mt-2 bg-red-500/10 px-3 py-1.5 rounded-lg">{clone.error_message}</p>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {clone.preview_url && (
                        <a href={clone.preview_url} target="_blank" rel="noreferrer"
                          className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-brand-400 transition-colors" title="Preview">
                          <Play size={16} />
                        </a>
                      )}
                      {clone.status === 'failed' && (
                        <button onClick={() => retryClone(clone.id)} title="Retry"
                          className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-amber-400 transition-colors">
                          <RefreshCw size={16} />
                        </button>
                      )}
                      <button onClick={() => deleteClone(clone.id)} title="Delete"
                        className="p-2 rounded-lg hover:bg-white/[0.04] text-surface-600 hover:text-red-400 transition-colors">
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                </div>
              </StaggerItem>
            );
          })}
        </StaggerContainer>
      )}
    </div>
  );
}
