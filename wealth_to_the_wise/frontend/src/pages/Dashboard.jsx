import { useState } from 'react';
import {
  Film,
  Upload,
  CalendarClock,
  Play,
  Pause,
  CheckCircle2,
  Clock,
  AlertTriangle,
} from 'lucide-react';

const stats = [
  { label: 'Total Generated', value: '24', icon: Film, color: 'text-brand-400' },
  { label: 'Posted', value: '18', icon: Upload, color: 'text-emerald-400' },
  { label: 'Next Scheduled', value: 'Today 6 PM', icon: CalendarClock, color: 'text-amber-400' },
];

const activity = [
  { id: 1, title: '10 Habits That Keep You Broke', status: 'posted', time: '2 hours ago', icon: CheckCircle2, color: 'text-emerald-400' },
  { id: 2, title: 'Why Budgeting Fails (And What Works)', status: 'scheduled', time: 'Today 6:00 PM', icon: Clock, color: 'text-amber-400' },
  { id: 3, title: 'The Truth About Index Funds', status: 'generating', time: 'In progress', icon: Film, color: 'text-brand-400' },
  { id: 4, title: 'Credit Score Myths Debunked', status: 'posted', time: '1 day ago', icon: CheckCircle2, color: 'text-emerald-400' },
  { id: 5, title: 'Side Hustles That Actually Pay', status: 'failed', time: '1 day ago', icon: AlertTriangle, color: 'text-red-400' },
];

export default function Dashboard() {
  const [automationOn, setAutomationOn] = useState(false);

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Dashboard</h1>
          <p className="text-sm text-surface-700 mt-1">Overview of your automation pipeline</p>
        </div>

        <button
          onClick={() => setAutomationOn(!automationOn)}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
            automationOn
              ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25'
              : 'bg-surface-200 text-surface-700 border border-surface-300 hover:bg-surface-300'
          }`}
        >
          {automationOn ? <Pause size={16} /> : <Play size={16} />}
          {automationOn ? 'Automation Running' : 'Start Automation'}
        </button>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {stats.map(({ label, value, icon: Icon, color }) => (
          <div
            key={label}
            className="bg-surface-100 border border-surface-300 rounded-xl p-5 flex items-center gap-4"
          >
            <div className="w-10 h-10 rounded-lg bg-surface-200 flex items-center justify-center">
              <Icon size={20} className={color} />
            </div>
            <div>
              <p className="text-xs text-surface-600 uppercase tracking-wider">{label}</p>
              <p className="text-lg font-semibold text-white mt-0.5">{value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Automation Status Banner */}
      {automationOn && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl px-5 py-4 flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <p className="text-sm text-emerald-300">
            Pipeline is active — videos are being generated and queued automatically.
          </p>
        </div>
      )}

      {/* Recent Activity */}
      <div>
        <h2 className="text-sm font-medium text-surface-700 uppercase tracking-wider mb-4">
          Recent Activity
        </h2>
        <div className="bg-surface-100 border border-surface-300 rounded-xl divide-y divide-surface-300">
          {activity.map(({ id, title, status, time, icon: Icon, color }) => (
            <div key={id} className="flex items-center gap-4 px-5 py-4">
              <div className="w-8 h-8 rounded-lg bg-surface-200 flex items-center justify-center shrink-0">
                <Icon size={16} className={color} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-surface-900 truncate">{title}</p>
                <p className="text-xs text-surface-600 mt-0.5">{time}</p>
              </div>
              <span
                className={`text-xs font-medium px-2.5 py-1 rounded-full capitalize ${
                  status === 'posted'
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : status === 'scheduled'
                    ? 'bg-amber-500/15 text-amber-400'
                    : status === 'failed'
                    ? 'bg-red-500/15 text-red-400'
                    : 'bg-brand-500/15 text-brand-400'
                }`}
              >
                {status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
