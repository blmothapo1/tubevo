import { useState, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../lib/api';
import VoiceStylePicker from './VoiceStylePicker';
import HookVariations from './HookVariations';
import CreatorControls from './CreatorControls';
import {
  ArrowLeft,
  ArrowRight,
  Clock,
  Search,
  Replace,
  RefreshCw,
  Sparkles,
  Type,
  X,
  Check,
} from 'lucide-react';

const ease = [0.25, 0.1, 0.25, 1];

const TONES = [
  { key: 'educational', label: 'Educational' },
  { key: 'energetic', label: 'Energetic' },
  { key: 'dramatic', label: 'Dramatic' },
  { key: 'humorous', label: 'Humorous' },
  { key: 'documentary', label: 'Documentary' },
];

/**
 * ScriptRefiner — full-screen editing panel for the two-phase creation flow.
 *
 * Props:
 *   script       - string          the generated script
 *   metadata     - object          title, description, tags
 *   readTime     - object          { words, minutes, display }
 *   topic        - string          the original topic
 *   videoId      - string          the record ID from generate-script
 *   onBack       - () => void      return to topic input
 *   onProduce    - (data) => void  kick off the render with final data
 */
export default function ScriptRefiner({ script: initialScript, metadata: initialMetadata, readTime: initialReadTime, topic, videoId, onBack, onProduce }) {
  const [script, setScript] = useState(initialScript);
  const [metadata, setMetadata] = useState(initialMetadata);
  const [readTime, setReadTime] = useState(initialReadTime);
  const [voiceStyle, setVoiceStyle] = useState('storyteller');
  const [activeTone, setActiveTone] = useState(null);
  const [producing, setProducing] = useState(false);

  // Hook variations
  const [hooks, setHooks] = useState([]);
  const [hooksLoading, setHooksLoading] = useState(false);

  // Find & replace
  const [showReplace, setShowReplace] = useState(false);
  const [findText, setFindText] = useState('');
  const [replaceText, setReplaceText] = useState('');

  // Paragraph regeneration
  const [regenIdx, setRegenIdx] = useState(null);

  // Tone rewriting
  const [toneLoading, setToneLoading] = useState(false);

  // Creator controls
  const [emphasisKeywords, setEmphasisKeywords] = useState('');
  const [humor, setHumor] = useState(false);
  const [audienceLevel, setAudienceLevel] = useState('general');

  // Message banner
  const [message, setMessage] = useState({ type: '', text: '' });

  const textareaRef = useRef(null);

  // Recalculate read time whenever script changes
  useEffect(() => {
    const words = script.split(/\s+/).filter(Boolean).length;
    const totalSec = Math.round((words / 150) * 60);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    setReadTime({ words, minutes: +(words / 150).toFixed(2), display: `${m}:${String(s).padStart(2, '0')}` });
  }, [script]);

  // ── Find & Replace ────────────────────────────────────────────────
  function handleReplace() {
    if (!findText) return;
    const newScript = script.replaceAll(findText, replaceText);
    if (newScript === script) {
      setMessage({ type: 'info', text: `"${findText}" not found in script.` });
      return;
    }
    setScript(newScript);
    setMessage({ type: 'success', text: `Replaced all instances of "${findText}".` });
    setFindText('');
    setReplaceText('');
  }

  // ── Generate Hook Variations ──────────────────────────────────────
  const handleGenerateHooks = useCallback(async () => {
    setHooksLoading(true);
    setMessage({ type: '', text: '' });
    try {
      const { data } = await api.post('/api/videos/generate-hooks', { script, topic });
      setHooks(data.hooks || []);
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to generate hooks.' });
    } finally {
      setHooksLoading(false);
    }
  }, [script, topic]);

  function handleSelectHook(hookText) {
    const paragraphs = script.split('\n\n');
    if (paragraphs.length > 0) {
      paragraphs[0] = hookText;
      setScript(paragraphs.join('\n\n'));
      setMessage({ type: 'success', text: 'Hook updated.' });
    }
  }

  // ── Regenerate Paragraph ──────────────────────────────────────────
  async function handleRegenParagraph(idx) {
    setRegenIdx(idx);
    setMessage({ type: '', text: '' });
    try {
      const { data } = await api.post('/api/videos/regenerate-paragraph', {
        script,
        topic,
        paragraph_index: idx,
      });
      const paragraphs = script.split('\n\n').filter(p => p.trim());
      paragraphs[idx] = data.new_paragraph;
      setScript(paragraphs.join('\n\n'));
      setMessage({ type: 'success', text: `Paragraph ${idx + 1} refreshed.` });
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to regenerate paragraph.' });
    } finally {
      setRegenIdx(null);
    }
  }

  // ── Apply Tone ────────────────────────────────────────────────────
  async function handleApplyTone(tone) {
    setToneLoading(true);
    setActiveTone(tone);
    setMessage({ type: '', text: '' });
    try {
      const { data } = await api.post('/api/videos/apply-tone', { script, tone });
      setScript(data.script);
      setReadTime(data.read_time);
      setMessage({ type: 'success', text: `Script rewritten in ${tone} tone.` });
    } catch (err) {
      setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to apply tone.' });
    } finally {
      setToneLoading(false);
    }
  }

  // ── Produce Video ─────────────────────────────────────────────────
  async function handleProduce() {
    setProducing(true);
    setMessage({ type: '', text: '' });
    onProduce({
      videoId,
      script,
      topic,
      voiceStyle,
      metadata,
    });
  }

  // Split script into paragraphs for paragraph-level controls
  const paragraphs = script.split('\n\n').filter(p => p.trim());

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.35, ease }}
      className="space-y-5"
    >
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="p-2 rounded-lg text-surface-600 hover:text-white hover:bg-surface-200/60 transition-all"
          >
            <ArrowLeft size={16} />
          </button>
          <div>
            <h2 className="text-[17px] font-semibold text-white tracking-tight">
              Refine Your Script
            </h2>
            <p className="text-[11px] text-surface-600 mt-0.5">
              Edit, adjust tone, pick hooks — then produce
            </p>
          </div>
        </div>

        {/* Read time badge */}
        <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-surface-200/40">
          <Clock size={11} className="text-surface-500" />
          <span className="text-[11px] text-surface-700 tabular-nums font-medium">
            {readTime.display}
          </span>
          <span className="text-[10px] text-surface-500">
            · {readTime.words} words
          </span>
        </div>
      </div>

      {/* ── Step indicator ──────────────────────────────────────────── */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-surface-500 uppercase tracking-wider font-medium">Step 2 of 3</span>
        <div className="flex-1 h-[2px] rounded-full bg-surface-200 overflow-hidden">
          <div className="h-full w-2/3 rounded-full bg-brand-500" />
        </div>
      </div>

      {/* ── Two-column layout ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-5">
        {/* ── Left: Script Editor ────────────────────────────────────── */}
        <div className="space-y-4">
          {/* Title preview */}
          <div className="card px-5 py-4">
            <label className="text-[10px] text-surface-500 uppercase tracking-wider font-medium mb-1.5 block">
              Video Title
            </label>
            <input
              type="text"
              value={metadata.title || ''}
              onChange={(e) => setMetadata({ ...metadata, title: e.target.value })}
              className="input-premium w-full text-sm font-medium"
            />
          </div>

          {/* Toolbar */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Find & Replace */}
            <button
              type="button"
              onClick={() => setShowReplace(!showReplace)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all
                ${showReplace
                  ? 'bg-brand-500/10 text-brand-400 ring-1 ring-brand-500/20'
                  : 'bg-surface-200/40 text-surface-600 hover:bg-surface-200/70'
                }
              `}
            >
              <Replace size={11} />
              Find & Replace
            </button>

            {/* Tone selector pills */}
            <div className="flex items-center gap-1">
              <Type size={11} className="text-surface-500 mr-1" />
              {TONES.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => handleApplyTone(t.key)}
                  disabled={toneLoading}
                  className={`px-2.5 py-1 rounded-md text-[10px] font-medium transition-all
                    ${activeTone === t.key
                      ? 'bg-brand-500/10 text-brand-400 ring-1 ring-brand-500/20'
                      : 'bg-surface-200/40 text-surface-600 hover:bg-surface-200/70'
                    }
                    disabled:opacity-40
                  `}
                >
                  {toneLoading && activeTone === t.key ? (
                    <RefreshCw size={10} className="animate-spin inline mr-1" />
                  ) : null}
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Find & Replace panel */}
          <AnimatePresence>
            {showReplace && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2, ease }}
                className="overflow-hidden"
              >
                <div className="flex items-center gap-2 p-3 rounded-xl bg-surface-200/30">
                  <div className="flex-1 flex items-center gap-2">
                    <Search size={12} className="text-surface-500 shrink-0" />
                    <input
                      type="text"
                      value={findText}
                      onChange={(e) => setFindText(e.target.value)}
                      placeholder="Find…"
                      className="bg-transparent text-xs text-white placeholder:text-surface-500 outline-none flex-1"
                    />
                  </div>
                  <ArrowRight size={12} className="text-surface-500 shrink-0" />
                  <div className="flex-1">
                    <input
                      type="text"
                      value={replaceText}
                      onChange={(e) => setReplaceText(e.target.value)}
                      placeholder="Replace with…"
                      className="bg-transparent text-xs text-white placeholder:text-surface-500 outline-none w-full"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleReplace}
                    disabled={!findText}
                    className="px-3 py-1 rounded-md bg-brand-500/10 text-brand-400 text-[11px] font-medium hover:bg-brand-500/20 transition-all disabled:opacity-40"
                  >
                    Replace All
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowReplace(false)}
                    className="p-1 text-surface-500 hover:text-surface-700 transition-colors"
                  >
                    <X size={12} />
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Script paragraphs with per-paragraph controls */}
          <div className="card p-5 space-y-0.5">
            <label className="text-[10px] text-surface-500 uppercase tracking-wider font-medium mb-3 block">
              Script — click any paragraph to edit, or use the full editor below
            </label>

            {paragraphs.map((para, idx) => (
              <div key={idx} className="group relative">
                <div className="py-2 px-3 rounded-lg hover:bg-surface-200/30 transition-colors">
                  <p className="text-[13px] leading-relaxed text-surface-800 whitespace-pre-wrap">
                    {para}
                  </p>
                  {/* Paragraph-level regen button (visible on hover) */}
                  <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      type="button"
                      onClick={() => handleRegenParagraph(idx)}
                      disabled={regenIdx !== null}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-surface-300/60 hover:bg-surface-300 text-[10px] text-surface-600 hover:text-white transition-all disabled:opacity-40"
                      title="Regenerate this paragraph"
                    >
                      {regenIdx === idx ? (
                        <RefreshCw size={9} className="animate-spin" />
                      ) : (
                        <Sparkles size={9} />
                      )}
                      Rewrite
                    </button>
                  </div>
                </div>
                {idx < paragraphs.length - 1 && (
                  <div className="h-px bg-surface-200/30 mx-3" />
                )}
              </div>
            ))}

            {/* Full text editor */}
            <div className="pt-4 mt-2 border-t border-surface-200/30">
              <label className="text-[10px] text-surface-500 uppercase tracking-wider font-medium mb-2 block">
                Full Editor
              </label>
              <textarea
                ref={textareaRef}
                value={script}
                onChange={(e) => setScript(e.target.value)}
                rows={12}
                className="w-full bg-surface-100/50 text-[13px] leading-relaxed text-surface-800 rounded-xl px-4 py-3 border border-[var(--border-subtle)] focus:border-brand-500/30 focus:ring-1 focus:ring-brand-500/10 outline-none resize-y transition-all"
              />
            </div>
          </div>
        </div>

        {/* ── Right sidebar: Controls ────────────────────────────────── */}
        <div className="space-y-5">
          {/* Voice Style */}
          <div className="card p-4">
            <VoiceStylePicker selected={voiceStyle} onChange={setVoiceStyle} />
          </div>

          {/* Hook Variations */}
          <div className="card p-4">
            <HookVariations
              hooks={hooks}
              currentHook={paragraphs[0] || ''}
              loading={hooksLoading}
              onSelect={handleSelectHook}
              onGenerate={handleGenerateHooks}
            />
          </div>

          {/* Advanced Controls */}
          <div className="card p-4">
            <CreatorControls
              emphasisKeywords={emphasisKeywords}
              onEmphasisChange={setEmphasisKeywords}
              humor={humor}
              onHumorChange={setHumor}
              audienceLevel={audienceLevel}
              onAudienceChange={setAudienceLevel}
            />
          </div>
        </div>
      </div>

      {/* ── Message banner ──────────────────────────────────────────── */}
      <AnimatePresence mode="wait">
        {message.text && (
          <motion.div
            key={message.text}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className={`text-xs px-3 py-2.5 rounded-lg ${
              message.type === 'error'
                ? 'bg-red-500/6 text-red-400'
                : message.type === 'info'
                ? 'bg-brand-500/6 text-brand-400'
                : 'bg-emerald-500/6 text-emerald-400'
            }`}
          >
            {message.text}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Bottom CTA bar ──────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4 pt-2">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-medium text-surface-600 hover:text-white bg-surface-200/40 hover:bg-surface-200/70 transition-all"
        >
          <ArrowLeft size={13} />
          Back
        </button>

        <motion.button
          type="button"
          onClick={handleProduce}
          disabled={producing || !script.trim()}
          whileHover={!producing ? { scale: 1.01 } : {}}
          whileTap={!producing ? { scale: 0.99 } : {}}
          className="btn-primary flex items-center gap-2 px-6 py-2.5"
        >
          {producing ? (
            <>
              <RefreshCw size={13} className="animate-spin" />
              Starting render…
            </>
          ) : (
            <>
              Produce Video
              <ArrowRight size={13} />
            </>
          )}
        </motion.button>
      </div>
    </motion.div>
  );
}
