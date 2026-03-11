/**
 * Skeleton loader components — used instead of spinners for a premium feel.
 */

export function SkeletonLine({ className = '', width = 'w-full' }) {
  return <div className={`skeleton h-4 ${width} ${className}`} />;
}

export function SkeletonCard({ className = '' }) {
  return (
    <div className={`card p-6 space-y-4 ${className}`}>
      <div className="skeleton h-5 w-1/3 rounded-[6px]" />
      <div className="skeleton h-4 w-2/3 rounded-[6px]" />
      <div className="skeleton h-4 w-1/2 rounded-[6px]" />
    </div>
  );
}

export function SkeletonStatCards() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {[0, 1, 2].map((i) => (
        <div key={i} className="card p-5 flex items-center gap-3">
          <div className="skeleton w-10 h-10 rounded-[10px]" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-3 w-20 rounded-[6px]" />
            <div className="skeleton h-6 w-12 rounded-[6px]" />
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
          <div className="skeleton w-24 h-14 rounded-[10px] hidden sm:block" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-4 w-3/4 rounded-[6px]" />
            <div className="skeleton h-3 w-1/2 rounded-[6px]" />
          </div>
          <div className="skeleton h-5 w-16 rounded-[6px]" />
        </div>
      ))}
    </div>
  );
}

/* ── Team page skeleton — team list cards ── */
export function SkeletonTeamList() {
  return (
    <div className="grid gap-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="card p-5">
          <div className="flex items-center gap-4">
            <div className="skeleton w-11 h-11 rounded-[12px]" />
            <div className="flex-1 space-y-2">
              <div className="skeleton h-4 w-1/3 rounded-[6px]" />
              <div className="skeleton h-3 w-1/4 rounded-[6px]" />
            </div>
            <div className="skeleton w-4 h-4 rounded-[4px]" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Team detail skeleton — header + member rows ── */
export function SkeletonTeamDetail() {
  return (
    <div className="space-y-5">
      {/* Header area */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="skeleton h-3 w-20 rounded-[6px]" />
          <div className="skeleton h-5 w-40 rounded-[6px]" />
        </div>
        <div className="flex items-center gap-2">
          <div className="skeleton h-8 w-20 rounded-[8px]" />
          <div className="skeleton h-8 w-24 rounded-[8px]" />
        </div>
      </div>
      {/* Tab bar */}
      <div className="skeleton h-9 w-48 rounded-[10px]" />
      {/* Member rows */}
      <div className="card divide-y divide-[var(--border-subtle)] overflow-hidden">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-3 px-5 py-3">
            <div className="skeleton w-9 h-9 rounded-[10px]" />
            <div className="flex-1 space-y-2">
              <div className="skeleton h-3.5 w-1/3 rounded-[6px]" />
              <div className="skeleton h-3 w-1/4 rounded-[6px]" />
            </div>
            <div className="skeleton h-5 w-14 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Referrals page skeleton — share card + stat cards + list ── */
export function SkeletonReferralPage() {
  return (
    <div className="space-y-6">
      {/* Share card placeholder */}
      <div className="card p-5 space-y-3">
        <div className="skeleton h-4 w-1/4 rounded-[6px]" />
        <div className="flex items-center gap-2">
          <div className="skeleton h-10 flex-1 rounded-[8px]" />
          <div className="skeleton h-10 w-20 rounded-[8px]" />
        </div>
      </div>
      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="card p-4 space-y-3">
            <div className="flex items-center gap-2">
              <div className="skeleton w-8 h-8 rounded-[8px]" />
              <div className="skeleton h-3 w-16 rounded-[6px]" />
            </div>
            <div className="skeleton h-6 w-12 rounded-[6px]" />
            <div className="skeleton h-3 w-20 rounded-[6px]" />
          </div>
        ))}
      </div>
      {/* How it works placeholder */}
      <div className="card p-5 space-y-3">
        <div className="skeleton h-4 w-1/3 rounded-[6px]" />
        <div className="skeleton h-3 w-2/3 rounded-[6px]" />
        <div className="skeleton h-3 w-1/2 rounded-[6px]" />
      </div>
      {/* Referred list placeholder */}
      <div className="card">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex items-center gap-3 p-4">
            <div className="skeleton w-8 h-8 rounded-full" />
            <div className="flex-1 space-y-2">
              <div className="skeleton h-3.5 w-1/3 rounded-[6px]" />
              <div className="skeleton h-3 w-1/5 rounded-[6px]" />
            </div>
            <div className="skeleton h-5 w-16 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Trend Radar skeleton — header + stats + filter tabs + cards ── */
export function SkeletonTrendRadar() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="space-y-2">
          <div className="skeleton h-6 w-40 rounded-[6px]" />
          <div className="skeleton h-4 w-64 rounded-[6px]" />
        </div>
        <div className="flex items-center gap-2">
          <div className="skeleton h-9 w-24 rounded-[8px]" />
          <div className="skeleton h-9 w-28 rounded-[8px]" />
        </div>
      </div>
      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="card p-4 flex items-center gap-3">
            <div className="skeleton w-9 h-9 rounded-[10px]" />
            <div className="flex-1 space-y-2">
              <div className="skeleton h-3 w-16 rounded-[6px]" />
              <div className="skeleton h-5 w-8 rounded-[6px]" />
            </div>
          </div>
        ))}
      </div>
      {/* Filter tabs */}
      <div className="skeleton h-9 w-72 rounded-[10px]" />
      {/* Trend cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="card p-5 space-y-3">
            <div className="flex items-center gap-2">
              <div className="skeleton w-6 h-6 rounded-full" />
              <div className="skeleton h-4 w-2/3 rounded-[6px]" />
            </div>
            <div className="skeleton h-3 w-full rounded-[6px]" />
            <div className="skeleton h-3 w-4/5 rounded-[6px]" />
            <div className="flex items-center gap-2 pt-2">
              <div className="skeleton h-8 w-20 rounded-[8px]" />
              <div className="skeleton h-8 w-20 rounded-[8px]" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
