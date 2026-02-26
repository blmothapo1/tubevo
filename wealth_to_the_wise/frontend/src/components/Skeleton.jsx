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
        <div key={i} className="card p-5 flex items-center gap-3">
          <div className="skeleton w-10 h-10 rounded" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-3 w-20" />
            <div className="skeleton h-5 w-12" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SkeletonVideoList() {
  return (
    <div className="card">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-3 p-4">
          <div className="skeleton w-24 h-14 rounded hidden sm:block" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-4 w-3/4" />
            <div className="skeleton h-3 w-1/2" />
          </div>
          <div className="skeleton h-5 w-16 rounded" />
        </div>
      ))}
    </div>
  );
}
