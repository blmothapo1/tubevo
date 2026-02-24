import { Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';

export default function Spinner({ className = '' }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="inline-flex"
    >
      <Loader2 className={`animate-spin text-brand-400 ${className}`} size={24} />
    </motion.div>
  );
}
