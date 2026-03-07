import { Mic, BookOpen, Zap, Coffee, Drama } from 'lucide-react';

const VOICE_STYLES = [
  {
    key: 'storyteller',
    label: 'Storyteller',
    description: 'Warm and engaging, like a great podcast host',
    icon: BookOpen,
    color: 'text-amber-400',
    bg: 'bg-amber-500/8',
    ring: 'ring-amber-500/30',
  },
  {
    key: 'documentary',
    label: 'Documentary',
    description: 'Measured and authoritative, premium feel',
    icon: Mic,
    color: 'text-blue-400',
    bg: 'bg-blue-500/8',
    ring: 'ring-blue-500/30',
  },
  {
    key: 'energetic',
    label: 'Energetic',
    description: 'High energy and punchy, top-tier creator',
    icon: Zap,
    color: 'text-emerald-400',
    bg: 'bg-emerald-500/8',
    ring: 'ring-emerald-500/30',
  },
  {
    key: 'calm',
    label: 'Calm Explainer',
    description: 'Relaxed and clear, expert breakdown',
    icon: Coffee,
    color: 'text-purple-400',
    bg: 'bg-purple-500/8',
    ring: 'ring-purple-500/30',
  },
  {
    key: 'dramatic',
    label: 'Dramatic',
    description: 'Intense and cinematic, trailer energy',
    icon: Drama,
    color: 'text-red-400',
    bg: 'bg-red-500/8',
    ring: 'ring-red-500/30',
  },
];

export default function VoiceStylePicker({ selected, onChange }) {
  return (
    <div className="space-y-2">
      <label className="text-[11px] text-surface-600 uppercase tracking-[0.08em] font-medium">
        Voice Style
      </label>
      <div className="grid gap-1.5">
        {VOICE_STYLES.map((style) => {
          const Icon = style.icon;
          const isActive = selected === style.key;
          return (
            <button
              key={style.key}
              type="button"
              onClick={() => onChange(style.key)}
              className={`
                relative flex items-center gap-3 px-3 py-2.5 rounded-lg
                text-left transition-all duration-150 cursor-pointer overflow-hidden
                ${isActive
                  ? `${style.bg} ring-1 ${style.ring}`
                  : 'bg-surface-200/40 hover:bg-surface-200/70 ring-1 ring-transparent'
                }
              `}
            >
              <div className={`w-7 h-7 rounded-md ${style.bg} flex items-center justify-center shrink-0`}>
                <Icon size={13} className={style.color} />
              </div>
              <div className="min-w-0 flex-1">
                <p className={`text-[11px] font-medium leading-tight ${isActive ? 'text-white' : 'text-surface-800'}`}>
                  {style.label}
                </p>
                <p className="text-[10px] text-surface-600 leading-tight mt-0.5 truncate">
                  {style.description}
                </p>
              </div>
              {isActive && (
                <div className={`w-1.5 h-1.5 rounded-full ${style.color.replace('text-', 'bg-')} shrink-0`} />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
