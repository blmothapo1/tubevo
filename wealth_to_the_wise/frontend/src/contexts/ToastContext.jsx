import { createContext, useContext, useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, AlertTriangle, Info, X, XCircle } from 'lucide-react';

/**
 * Global toast notification system.
 *
 * Usage:
 *   const toast = useToast();
 *   toast.success('Video generated!');
 *   toast.error('Something went wrong');
 *   toast.info('Processing your request…');
 *   toast.warning('Approaching your monthly limit');
 */

const ToastContext = createContext(null);

const TOAST_ICONS = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const TOAST_COLORS = {
  success: {
    bg: 'rgba(16, 185, 129, 0.08)',
    border: 'rgba(16, 185, 129, 0.2)',
    icon: 'text-emerald-400',
    progress: 'bg-emerald-500',
  },
  error: {
    bg: 'rgba(239, 68, 68, 0.08)',
    border: 'rgba(239, 68, 68, 0.2)',
    icon: 'text-red-400',
    progress: 'bg-red-500',
  },
  warning: {
    bg: 'rgba(245, 158, 11, 0.08)',
    border: 'rgba(245, 158, 11, 0.2)',
    icon: 'text-amber-400',
    progress: 'bg-amber-500',
  },
  info: {
    bg: 'rgba(99, 102, 241, 0.08)',
    border: 'rgba(99, 102, 241, 0.2)',
    icon: 'text-brand-400',
    progress: 'bg-brand-500',
  },
};

const DEFAULT_DURATION = 4000;
let toastIdCounter = 0;

function Toast({ id, type, message, duration, onDismiss }) {
  const Icon = TOAST_ICONS[type] || Info;
  const colors = TOAST_COLORS[type] || TOAST_COLORS.info;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -8, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.96, transition: { duration: 0.15 } }}
      transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
      className="pointer-events-auto w-full max-w-[400px] rounded-xl overflow-hidden shadow-lg shadow-black/20"
      style={{
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        backdropFilter: 'blur(16px)',
      }}
    >
      <div className="flex items-start gap-3 px-4 py-3.5">
        <Icon size={16} className={`${colors.icon} mt-0.5 shrink-0`} />
        <p className="flex-1 text-[13px] text-white/90 font-medium leading-relaxed">
          {message}
        </p>
        <button
          onClick={() => onDismiss(id)}
          className="shrink-0 mt-0.5 text-surface-600 hover:text-white transition-colors duration-150"
        >
          <X size={14} />
        </button>
      </div>
      {/* Progress bar */}
      <motion.div
        initial={{ scaleX: 1 }}
        animate={{ scaleX: 0 }}
        transition={{ duration: duration / 1000, ease: 'linear' }}
        className={`h-[2px] ${colors.progress} origin-left opacity-40`}
      />
    </motion.div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timersRef = useRef({});

  const dismiss = useCallback((id) => {
    clearTimeout(timersRef.current[id]);
    delete timersRef.current[id];
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((type, message, duration = DEFAULT_DURATION) => {
    const id = ++toastIdCounter;
    setToasts((prev) => [...prev.slice(-4), { id, type, message, duration }]); // max 5 visible
    timersRef.current[id] = setTimeout(() => dismiss(id), duration);
    return id;
  }, [dismiss]);

  const api = useCallback(() => ({
    success: (msg, dur) => addToast('success', msg, dur),
    error: (msg, dur) => addToast('error', msg, dur ?? 6000),
    warning: (msg, dur) => addToast('warning', msg, dur),
    info: (msg, dur) => addToast('info', msg, dur),
    dismiss,
  }), [addToast, dismiss]);

  return (
    <ToastContext.Provider value={api()}>
      {children}
      {/* Toast container — top-right, above everything */}
      <div
        className="fixed top-4 right-4 z-[9999] flex flex-col items-end gap-2 pointer-events-none"
        aria-live="polite"
        aria-atomic="true"
      >
        <AnimatePresence mode="popLayout">
          {toasts.map((t) => (
            <Toast
              key={t.id}
              id={t.id}
              type={t.type}
              message={t.message}
              duration={t.duration}
              onDismiss={dismiss}
            />
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within <ToastProvider>');
  return ctx;
}
