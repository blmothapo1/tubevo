/**
 * Skeleton loader components — used instead of spinners for a premium feel.
 */

export function SkeletonLine({ className = '', width = 'w-full' }) {
  return <div className={`skeleton h-4 ${width} ${className}`} />;
}

export function SkeletonCard({ className = '' }) {
  return (
    <div className={`card p-6 space-y-4 ${className}`}>
      <div className="skeleton h-5 w-1/3" />
      <div className="skeleton h-4 w-2/3" />
      <div className="skeleton h-4 w-1/2" />
    </div>
  );
}

export function SkeletonStatCards() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
      {[0, 1, 2].map((i) => (
        <div key={i} className="card p-6 flex items-center gap-4">
          <div className="skeleton w-12 h-12 rounded-xl" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-3 w-20" />
            <div className="skeleton h-6 w-12" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SkeletonVideoList() {
  return (
    <div className="card divide-y divide-surface-300/50">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-4 p-5">
          <div className="skeleton w-28 h-16 rounded-xl hidden sm:block" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-4 w-3/4" />
            <div className="skeleton h-3 w-1/2" />
          </div>
          <div className="skeleton h-6 w-20 rounded-full" />
        </div>
      ))}
    </div>
  );
}
