import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, Check, RefreshCw } from 'lucide-react';

const ease = [0.25, 0.1, 0.25, 1];

/**
 * HookVariations — displays selectable alternate hooks for a script.
 *
 * Props:
 *   hooks       - string[]  array of hook texts
 *   currentHook - string    the current opening paragraph
 *   loading     - boolean   true while hooks are being generated
 *   onSelect    - (hook: string) => void — called when the user picks a hook
 *   onGenerate  - () => void — called to request new hook variations
 */
export default function HookVariations({ hooks, currentHook, loading, onSelect, onGenerate }) {
  const [selectedIdx, setSelectedIdx] = useState(null);

  function handleSelect(idx) {
    setSelectedIdx(idx);
    onSelect(hooks[idx]);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="text-[11px] text-surface-600 uppercase tracking-[0.08em] font-medium">
          Hook Variations
        </label>
        <button
          type="button"
          onClick={onGenerate}
          disabled={loading}
          className="inline-flex items-center gap-1.5 text-[11px] text-brand-400 hover:text-brand-300 transition-colors disabled:opacity-50"
        >
          {loading ? (
            <RefreshCw size={11} className="animate-spin" />
          ) : (
            <Sparkles size={11} />
          )}
          {loading ? 'Generating…' : hooks.length > 0 ? 'Regenerate' : 'Generate 3 Hooks'}
        </button>
      </div>

      <AnimatePresence mode="wait">
        {hooks.length === 0 && !loading && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-[11px] text-surface-500 italic"
          >
            Generate alternate hooks to test different openings for your video.
          </motion.p>
        )}

        {loading && (
          <motion.div
            key="loading"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="flex items-center gap-2 py-4 justify-center"
          >
            <RefreshCw size={14} className="text-brand-400 animate-spin" />
            <span className="text-xs text-surface-600">Crafting alternate hooks…</span>
          </motion.div>
        )}

        {!loading && hooks.length > 0 && (
          <motion.div
            key="hooks"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.25, ease }}
            className="space-y-2"
          >
            {hooks.map((hook, idx) => {
              const isSelected = selectedIdx === idx;
              return (
                <motion.button
                  key={idx}
                  type="button"
                  onClick={() => handleSelect(idx)}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.08, duration: 0.2 }}
                  className={`
                    w-full text-left px-3.5 py-3 rounded-xl transition-all duration-200
                    ${isSelected
                      ? 'bg-brand-500/8 ring-1 ring-brand-500/30'
                      : 'bg-surface-200/40 hover:bg-surface-200/70 ring-1 ring-transparent'
                    }
                  `}
                >
                  <div className="flex items-start gap-2.5">
                    <div className={`
                      w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5
                      ${isSelected ? 'bg-brand-500' : 'bg-surface-300/60'}
                    `}>
                      {isSelected ? (
                        <Check size={10} className="text-white" />
                      ) : (
                        <span className="text-[9px] text-surface-600 font-semibold">{idx + 1}</span>
                      )}
                    </div>
                    <p className={`text-[11px] leading-relaxed ${isSelected ? 'text-white' : 'text-surface-800'}`}>
                      {hook}
                    </p>
                  </div>
                </motion.button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
