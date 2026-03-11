import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';

/**
 * Full-screen loading spinner shown while lazy-loaded pages resolve.
 * Matches the Tubevo design language — subtle, fast, dark.
 */
export default function PageLoader() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.2, delay: 0.1 }}
        className="flex flex-col items-center gap-3"
      >
        <Loader2 size={24} className="text-brand-400 animate-spin" />
        <p className="text-[12px] text-surface-600 font-medium">Loading…</p>
      </motion.div>
    </div>
  );
}
