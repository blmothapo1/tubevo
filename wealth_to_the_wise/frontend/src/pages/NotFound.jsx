import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Home, ArrowLeft } from 'lucide-react';

/**
 * 404 — Not Found page.
 * Catches any route that doesn't match a defined path.
 */
export default function NotFound() {
  return (
    <div className="min-h-screen bg-surface-50 flex items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.25, 0.1, 0.25, 1] }}
        className="max-w-md w-full text-center"
      >
        {/* 404 number */}
        <p className="text-[72px] sm:text-[96px] font-bold text-gradient leading-none mb-2 tracking-tighter">
          404
        </p>

        {/* Heading */}
        <h1 className="text-[20px] font-semibold text-white mb-2 tracking-tight">
          Page not found
        </h1>
        <p className="text-[14px] text-surface-600 leading-relaxed mb-10">
          The page you're looking for doesn't exist or has been moved.
        </p>

        {/* Actions */}
        <div className="flex items-center justify-center gap-3">
          <Link
            to="/dashboard"
            className="btn-primary !rounded-[10px] !px-5 !py-2.5 !text-[13px] inline-flex items-center gap-2"
          >
            <Home size={14} />
            Go to Dashboard
          </Link>
          <button
            onClick={() => window.history.back()}
            className="px-5 py-2.5 rounded-[10px] text-[13px] font-medium text-surface-700 hover:text-white hover:bg-white/[0.06] transition-all duration-150 inline-flex items-center gap-2"
          >
            <ArrowLeft size={14} />
            Go Back
          </button>
        </div>

        {/* Branding */}
        <p className="mt-16 text-[11px] text-surface-500">
          Tubevo
        </p>
      </motion.div>
    </div>
  );
}
