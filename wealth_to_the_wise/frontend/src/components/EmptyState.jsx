import { motion } from 'framer-motion';

const ease = [0.25, 0.1, 0.25, 1];

/**
 * Shared empty state — consistent across all pages.
 *
 * @param {import('lucide-react').LucideIcon} icon — Lucide icon component
 * @param {string} title — Main heading
 * @param {string} description — Supporting text
 * @param {React.ReactNode} [action] — Optional CTA button/link
 */
export default function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.1, ease }}
      className="card px-6 py-16 text-center"
    >
      {Icon && (
        <div className="w-14 h-14 rounded-[12px] bg-brand-500/10 flex items-center justify-center mx-auto mb-5">
          <Icon size={24} className="text-brand-400" />
        </div>
      )}
      <h3 className="text-[15px] font-semibold text-white mb-2">{title}</h3>
      {description && (
        <p className="text-[13px] text-surface-600 max-w-sm mx-auto leading-relaxed">
          {description}
        </p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </motion.div>
  );
}
