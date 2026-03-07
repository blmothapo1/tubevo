import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, Target, Smile, Users } from 'lucide-react';

const AUDIENCE_LEVELS = [
  { key: 'beginner', label: 'Beginner', desc: 'No prior knowledge assumed' },
  { key: 'general', label: 'General', desc: 'Broadly accessible' },
  { key: 'expert', label: 'Expert', desc: 'Deep, advanced content' },
];

const ease = [0.25, 0.1, 0.25, 1];

/**
 * CreatorControls — advanced, collapsible controls for script customization.
 *
 * Props:
 *   emphasisKeywords - string
 *   onEmphasisChange - (value: string) => void
 *   humor            - boolean
 *   onHumorChange    - (value: boolean) => void
 *   audienceLevel    - string
 *   onAudienceChange - (value: string) => void
 */
export default function CreatorControls({
  emphasisKeywords,
  onEmphasisChange,
  humor,
  onHumorChange,
  audienceLevel,
  onAudienceChange,
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[11px] text-surface-600 hover:text-surface-800 transition-colors uppercase tracking-[0.08em] font-medium"
      >
        Advanced Controls
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25, ease }}
            className="overflow-hidden"
          >
            <div className="space-y-4 pt-1">
              {/* Emphasis Keywords */}
              <div className="space-y-1.5">
                <label className="flex items-center gap-1.5 text-[11px] text-surface-600 font-medium">
                  <Target size={11} />
                  Topic Emphasis
                </label>
                <input
                  type="text"
                  value={emphasisKeywords}
                  onChange={(e) => onEmphasisChange(e.target.value)}
                  placeholder="e.g. compound interest, passive income, index funds"
                  className="input-premium w-full text-xs"
                />
                <p className="text-[10px] text-surface-500">
                  Keywords woven prominently throughout the script
                </p>
              </div>

              {/* Humor Toggle */}
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-1.5 text-[11px] text-surface-600 font-medium">
                  <Smile size={11} />
                  Add Humor
                </label>
                <button
                  type="button"
                  onClick={() => onHumorChange(!humor)}
                  className={`
                    relative w-9 h-5 rounded-full transition-colors duration-200
                    ${humor ? 'bg-brand-500' : 'bg-surface-300/60'}
                  `}
                >
                  <motion.div
                    className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm"
                    animate={{ left: humor ? 18 : 2 }}
                    transition={{ type: 'spring', stiffness: 500, damping: 30 }}
                  />
                </button>
              </div>

              {/* Audience Level */}
              <div className="space-y-1.5">
                <label className="flex items-center gap-1.5 text-[11px] text-surface-600 font-medium">
                  <Users size={11} />
                  Audience Level
                </label>
                <div className="flex gap-1">
                  {AUDIENCE_LEVELS.map((level) => {
                    const isActive = audienceLevel === level.key;
                    return (
                      <button
                        key={level.key}
                        type="button"
                        onClick={() => onAudienceChange(level.key)}
                        className={`
                          flex-1 py-1.5 px-2 rounded-md text-center transition-all duration-150
                          ${isActive
                            ? 'bg-brand-500/10 ring-1 ring-brand-500/30 text-brand-400'
                            : 'bg-surface-200/40 text-surface-600 hover:bg-surface-200/70'
                          }
                        `}
                      >
                        <span className="text-[10px] font-medium">{level.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
