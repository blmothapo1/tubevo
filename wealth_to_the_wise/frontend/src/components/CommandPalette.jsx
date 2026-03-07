import { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard, Film, CalendarClock, Settings, Tv2, Search,
  DollarSign, Image, Eye, Mic, Shield, ArrowRight, Command, Radar,
} from 'lucide-react';

const ALL_COMMANDS = [
  { id: 'dashboard', label: 'Dashboard', desc: 'Pipeline overview', icon: LayoutDashboard, path: '/dashboard', keywords: ['home', 'overview', 'stats'] },
  { id: 'videos', label: 'Videos', desc: 'Manage your videos', icon: Film, path: '/videos', keywords: ['content', 'create', 'list'] },
  { id: 'schedule', label: 'Schedule', desc: 'Recurring schedules', icon: CalendarClock, path: '/schedule', keywords: ['cron', 'recurring', 'auto'] },
  { id: 'settings', label: 'Settings', desc: 'Account & preferences', icon: Settings, path: '/settings', keywords: ['account', 'profile', 'api', 'keys'] },
  { id: 'trends', label: 'Trend Radar', desc: 'Detect & publish trends', icon: Radar, path: '/trends', keywords: ['trend', 'radar', 'autopilot', 'viral', 'detect', 'hot'] },
  { id: 'channels', label: 'Channels', desc: 'YouTube channels', icon: Tv2, path: '/channels', keywords: ['youtube', 'connect'] },
  { id: 'niche', label: 'Niche Intel', desc: 'Analyze niches & topics', icon: Search, path: '/niche', keywords: ['research', 'topic', 'trending', 'scan'] },
  { id: 'revenue', label: 'Revenue', desc: 'Track income', icon: DollarSign, path: '/revenue', keywords: ['money', 'earnings', 'adsense', 'income'] },
  { id: 'thumbnails', label: 'Thumbnails', desc: 'A/B testing', icon: Image, path: '/thumbnails', keywords: ['ab', 'test', 'ctr', 'click'] },
  { id: 'competitors', label: 'Competitors', desc: 'Monitor rivals', icon: Eye, path: '/competitors', keywords: ['spy', 'rival', 'monitor', 'track'] },
  { id: 'voices', label: 'Voice Clones', desc: 'Custom voice studio', icon: Mic, path: '/voices', keywords: ['voice', 'clone', 'tts', 'elevenlabs'] },
];

function fuzzyMatch(query, command) {
  const q = query.toLowerCase();
  const targets = [command.label, command.desc, ...command.keywords].map(s => s.toLowerCase());
  return targets.some(t => t.includes(q));
}

export default function CommandPalette({ open, onClose, onNavigate }) {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  const results = useMemo(() => {
    if (!query.trim()) return ALL_COMMANDS;
    return ALL_COMMANDS.filter(cmd => fuzzyMatch(query, cmd));
  }, [query]);

  // Reset on open
  useEffect(() => {
    if (open) {
      setQuery('');
      setSelected(0);
      // Focus after animation frame
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Keep selection in bounds
  useEffect(() => {
    setSelected(s => Math.min(s, Math.max(0, results.length - 1)));
  }, [results]);

  // Scroll selected into view
  useEffect(() => {
    const el = listRef.current?.children[selected];
    el?.scrollIntoView({ block: 'nearest' });
  }, [selected]);

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelected(s => (s + 1) % results.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelected(s => (s - 1 + results.length) % results.length);
    } else if (e.key === 'Enter' && results[selected]) {
      onNavigate(results[selected].path);
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[60]"
            onClick={onClose}
          />
          {/* Palette */}
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -10 }}
            transition={{ type: 'spring', stiffness: 500, damping: 35 }}
            className="fixed top-[20%] left-1/2 -translate-x-1/2 w-[90vw] max-w-[520px] z-[61] command-palette"
          >
            {/* Search input */}
            <div className="flex items-center gap-3 px-5 h-[52px] border-b border-[var(--border-subtle)]">
              <Search size={16} className="text-surface-500 shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Where do you want to go?"
                className="flex-1 bg-transparent text-[14px] text-white placeholder:text-surface-500 outline-none"
              />
              <kbd className="text-[10px] text-surface-500 bg-white/[0.04] px-1.5 py-0.5 rounded font-mono">esc</kbd>
            </div>

            {/* Results */}
            <div ref={listRef} className="max-h-[320px] overflow-y-auto py-2 scrollbar-none">
              {results.length === 0 ? (
                <div className="px-5 py-8 text-center">
                  <p className="text-surface-500 text-[13px]">No results for "{query}"</p>
                </div>
              ) : (
                results.map((cmd, i) => {
                  const Icon = cmd.icon;
                  const isSelected = i === selected;
                  return (
                    <button
                      key={cmd.id}
                      onClick={() => onNavigate(cmd.path)}
                      onMouseEnter={() => setSelected(i)}
                      className={`w-full flex items-center gap-3 px-5 py-2.5 text-left transition-colors duration-75
                        ${isSelected ? 'bg-brand-500/[0.08]' : 'hover:bg-white/[0.02]'}`}
                    >
                      <div className={`w-8 h-8 rounded-[8px] flex items-center justify-center shrink-0 transition-colors
                        ${isSelected ? 'bg-brand-500/15 text-brand-400' : 'bg-white/[0.03] text-surface-600'}`}>
                        <Icon size={16} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className={`text-[13px] font-medium truncate ${isSelected ? 'text-white' : 'text-surface-800'}`}>
                          {cmd.label}
                        </p>
                        <p className="text-[11px] text-surface-500 truncate">{cmd.desc}</p>
                      </div>
                      {isSelected && (
                        <ArrowRight size={14} className="text-brand-400 shrink-0" />
                      )}
                    </button>
                  );
                })
              )}
            </div>

            {/* Footer hint */}
            <div className="flex items-center gap-4 px-5 py-2.5 border-t border-[var(--border-subtle)]">
              <span className="flex items-center gap-1 text-[10px] text-surface-500">
                <kbd className="bg-white/[0.04] px-1 py-0.5 rounded font-mono">↑↓</kbd> navigate
              </span>
              <span className="flex items-center gap-1 text-[10px] text-surface-500">
                <kbd className="bg-white/[0.04] px-1 py-0.5 rounded font-mono">↵</kbd> open
              </span>
              <span className="flex items-center gap-1 text-[10px] text-surface-500">
                <kbd className="bg-white/[0.04] px-1 py-0.5 rounded font-mono">esc</kbd> close
              </span>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
