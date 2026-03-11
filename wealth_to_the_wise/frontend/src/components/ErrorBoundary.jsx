import { Component } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

/**
 * Global Error Boundary — catches any uncaught JS error in the React tree
 * and shows a branded recovery screen instead of a white page.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // Log to console (and future error reporting service)
    console.error('[ErrorBoundary] Uncaught error:', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleGoHome = () => {
    window.location.href = '/dashboard';
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-surface-50 flex items-center justify-center p-6">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: [0.25, 0.1, 0.25, 1] }}
            className="max-w-md w-full text-center"
          >
            {/* Icon */}
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-red-500/20 to-red-500/5 flex items-center justify-center mx-auto mb-6">
              <AlertTriangle size={28} className="text-red-400" />
            </div>

            {/* Heading */}
            <h1 className="text-[22px] font-semibold text-white mb-2 tracking-tight">
              Something went wrong
            </h1>
            <p className="text-[14px] text-surface-600 leading-relaxed mb-8">
              An unexpected error occurred. Your data is safe — try refreshing the page.
            </p>

            {/* Error detail (dev only) */}
            {import.meta.env.DEV && this.state.error && (
              <div className="mb-6 p-4 rounded-xl bg-red-500/5 border border-red-500/10 text-left">
                <p className="text-[11px] font-mono text-red-300 break-all leading-relaxed">
                  {this.state.error.message}
                </p>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={this.handleReload}
                className="btn-primary !rounded-[10px] !px-5 !py-2.5 !text-[13px] inline-flex items-center gap-2"
              >
                <RefreshCw size={14} />
                Refresh Page
              </button>
              <button
                onClick={this.handleGoHome}
                className="px-5 py-2.5 rounded-[10px] text-[13px] font-medium text-surface-700 hover:text-white hover:bg-white/[0.06] transition-all duration-150 inline-flex items-center gap-2"
              >
                <Home size={14} />
                Go Home
              </button>
            </div>

            {/* Branding */}
            <p className="mt-12 text-[11px] text-surface-500">
              Tubevo v{import.meta.env.VITE_APP_VERSION || '1.0'}
            </p>
          </motion.div>
        </div>
      );
    }

    return this.props.children;
  }
}
