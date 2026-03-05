import { FadeIn } from './Motion';

/**
 * Shared page header — consistent title + subtitle across all pages.
 *
 * @param {string} title — Page heading
 * @param {string} [subtitle] — Micro-label below heading
 * @param {React.ReactNode} [action] — Optional right-side CTA
 */
export default function PageHeader({ title, subtitle, action, className = '' }) {
  return (
    <FadeIn className={className}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[20px] sm:text-[24px] font-semibold text-white tracking-tight">
            {title}
          </h1>
          {subtitle && (
            <p className="text-[12px] text-surface-600 mt-2 uppercase tracking-[0.08em] font-medium">
              {subtitle}
            </p>
          )}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
    </FadeIn>
  );
}
