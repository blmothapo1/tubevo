import { ExternalLink, CalendarDays } from 'lucide-react';

const history = [
  {
    id: 1,
    title: '10 Habits That Keep You Broke',
    postedAt: '2025-01-19 18:02',
    youtubeUrl: 'https://youtube.com/watch?v=example1',
    views: 1243,
  },
  {
    id: 2,
    title: 'Credit Score Myths Debunked',
    postedAt: '2025-01-18 18:01',
    youtubeUrl: 'https://youtube.com/watch?v=example2',
    views: 876,
  },
  {
    id: 3,
    title: 'The Latte Factor Is a Lie',
    postedAt: '2025-01-17 18:00',
    youtubeUrl: 'https://youtube.com/watch?v=example3',
    views: 2105,
  },
  {
    id: 4,
    title: 'How Compound Interest Really Works',
    postedAt: '2025-01-16 18:00',
    youtubeUrl: 'https://youtube.com/watch?v=example4',
    views: 3412,
  },
  {
    id: 5,
    title: 'Emergency Fund: How Much Is Enough?',
    postedAt: '2025-01-15 18:01',
    youtubeUrl: 'https://youtube.com/watch?v=example5',
    views: 1890,
  },
];

function formatViews(n) {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export default function Schedule() {
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-white">Post History</h1>
        <p className="text-sm text-surface-700 mt-1">
          Videos that have been posted to your YouTube channel
        </p>
      </div>

      {/* Table */}
      <div className="bg-surface-100 border border-surface-300 rounded-xl overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-surface-300">
              <th className="px-5 py-3 text-xs font-medium text-surface-600 uppercase tracking-wider">
                Title
              </th>
              <th className="px-5 py-3 text-xs font-medium text-surface-600 uppercase tracking-wider">
                Posted
              </th>
              <th className="px-5 py-3 text-xs font-medium text-surface-600 uppercase tracking-wider">
                Views
              </th>
              <th className="px-5 py-3 text-xs font-medium text-surface-600 uppercase tracking-wider text-right">
                Link
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-300">
            {history.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-5 py-12 text-center text-surface-600 text-sm">
                  No videos posted yet.
                </td>
              </tr>
            ) : (
              history.map((item) => (
                <tr key={item.id} className="hover:bg-surface-200/50 transition-colors">
                  <td className="px-5 py-4">
                    <p className="text-sm font-medium text-surface-900 truncate max-w-xs">
                      {item.title}
                    </p>
                  </td>
                  <td className="px-5 py-4">
                    <span className="flex items-center gap-1.5 text-sm text-surface-700">
                      <CalendarDays size={14} className="text-surface-600" />
                      {item.postedAt}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <span className="text-sm text-surface-800 font-medium">
                      {formatViews(item.views)}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <a
                      href={item.youtubeUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-sm text-brand-400 hover:text-brand-300 transition-colors"
                    >
                      Watch <ExternalLink size={14} />
                    </a>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
