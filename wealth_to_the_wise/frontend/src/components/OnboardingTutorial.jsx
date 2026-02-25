// filepath: frontend/src/components/OnboardingTutorial.jsx
/**
 * Interactive Adobe-style guided onboarding tutorial.
 *
 * Shows a spotlight overlay that walks new users through the UI
 * step by step, highlighting elements with a glow/focus effect,
 * darkening the rest of the screen, and displaying tooltip
 * instructions with an animated pointer.
 *
 * 100 % additive — does not modify or break any existing logic.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  ChevronRight,
  ChevronLeft,
  X,
  MousePointerClick,
  Sparkles,
  Key,
  Mic,
  Wand2,
  Download,
  PartyPopper,
} from 'lucide-react';

const ease = [0.25, 0.1, 0.25, 1];

// ── Tutorial step definitions ────────────────────────────────
const STEPS = [
  {
    id: 'welcome',
    title: 'Welcome to Tubevo! 🎬',
    description:
      'Let\'s take a quick tour to get you set up. We\'ll walk through adding your API keys, generating your first video, and more.',
    icon: Sparkles,
    target: null, // No element — centered modal
    route: '/dashboard',
    position: 'center',
    duration: 8000,
  },
  {
    id: 'sidebar-nav',
    title: 'Navigation',
    description:
      'Use the menu button to open the sidebar. From here you can jump to your Dashboard, Videos, Schedule, and Settings.',
    icon: null,
    target: '[data-tour="menu-button"]',
    route: '/dashboard',
    position: 'right',
    duration: 8000,
  },
  {
    id: 'api-keys',
    title: 'Add Your API Keys',
    description:
      'Head to Settings → API Keys to paste your OpenAI, ElevenLabs, and Pexels keys. These power the script, voice, and footage.',
    icon: Key,
    target: '[data-tour="settings-apikeys-tab"]',
    route: '/settings?tab=apikeys',
    position: 'bottom',
    duration: 12000,
  },
  {
    id: 'topic-input',
    title: 'Enter Your Topic',
    description:
      'Type any topic you want a video about — e.g. "5 Habits of Wealthy People". The AI writes the script for you.',
    icon: Wand2,
    target: '[data-tour="topic-input"]',
    route: '/videos',
    position: 'bottom',
    duration: 10000,
  },
  {
    id: 'generate-button',
    title: 'Click Generate',
    description:
      'Hit the Generate button to kick off the full pipeline: script → voiceover → stock footage → video. It takes about 2–3 minutes.',
    icon: null,
    target: '[data-tour="generate-button"]',
    route: '/videos',
    position: 'left',
    duration: 10000,
  },
  {
    id: 'video-result',
    title: 'Download or Upload',
    description:
      'Once complete, your video appears in the list. You can download it or — if YouTube is connected — it uploads automatically!',
    icon: Download,
    target: '[data-tour="video-list"]',
    route: '/videos',
    position: 'top',
    duration: 10000,
  },
  {
    id: 'finish',
    title: 'You\'re All Set! 🎉',
    description:
      'That\'s it! Start creating amazing videos. You can replay this tutorial anytime from Settings → Account.',
    icon: PartyPopper,
    target: null,
    route: null,
    position: 'center',
    duration: 8000,
  },
];

// ── Spotlight overlay + tooltip component ────────────────────
export default function OnboardingTutorial({ onComplete }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [targetRect, setTargetRect] = useState(null);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const resizeObserverRef = useRef(null);
  const stepTimerRef = useRef(null);

  const step = STEPS[currentStep];
  const totalSteps = STEPS.length;
  const progress = ((currentStep + 1) / totalSteps) * 100;

  // ── Locate the target element and track its position ──────
  const updateTargetRect = useCallback(() => {
    if (!step.target) {
      setTargetRect(null);
      return;
    }

    // Small delay to let route transitions settle
    const timer = setTimeout(() => {
      const el = document.querySelector(step.target);
      if (el) {
        const rect = el.getBoundingClientRect();
        setTargetRect({
          top: rect.top,
          left: rect.left,
          width: rect.width,
          height: rect.height,
          centerX: rect.left + rect.width / 2,
          centerY: rect.top + rect.height / 2,
        });
      } else {
        setTargetRect(null);
      }
    }, 400);

    return () => clearTimeout(timer);
  }, [step.target]);

  // Navigate to the step's route if needed
  useEffect(() => {
    if (step.route) {
      const [path, query] = step.route.split('?');
      const currentPath = location.pathname;
      if (currentPath !== path) {
        setIsTransitioning(true);
        navigate(step.route);
        const timer = setTimeout(() => setIsTransitioning(false), 600);
        return () => clearTimeout(timer);
      }
    }
  }, [currentStep, step.route, navigate, location.pathname]);

  // Update target rect after navigation settles
  useEffect(() => {
    const cleanup = updateTargetRect();

    // Also listen for resize/scroll
    const handleUpdate = () => updateTargetRect();
    window.addEventListener('resize', handleUpdate);
    window.addEventListener('scroll', handleUpdate, true);

    return () => {
      if (cleanup) cleanup();
      window.removeEventListener('resize', handleUpdate);
      window.removeEventListener('scroll', handleUpdate, true);
    };
  }, [updateTargetRect, currentStep, isTransitioning]);

  // ── Step navigation ───────────────────────────────────────
  const goNext = useCallback(() => {
    if (currentStep < totalSteps - 1) {
      setTargetRect(null);
      setCurrentStep((s) => s + 1);
    } else {
      onComplete();
    }
  }, [currentStep, totalSteps, onComplete]);

  const goPrev = useCallback(() => {
    if (currentStep > 0) {
      setTargetRect(null);
      setCurrentStep((s) => s - 1);
    }
  }, [currentStep]);

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'ArrowRight' || e.key === 'Enter') goNext();
      if (e.key === 'ArrowLeft') goPrev();
      if (e.key === 'Escape') onComplete();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [goNext, goPrev, onComplete]);

  // ── Compute tooltip position ──────────────────────────────
  const getTooltipStyle = () => {
    if (step.position === 'center' || !targetRect) {
      return {
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
      };
    }

    const pad = 20;
    const tooltipW = 380;
    const tooltipH = 220;

    switch (step.position) {
      case 'bottom':
        return {
          position: 'fixed',
          top: Math.min(targetRect.top + targetRect.height + pad, window.innerHeight - tooltipH - 20),
          left: Math.max(20, Math.min(targetRect.centerX - tooltipW / 2, window.innerWidth - tooltipW - 20)),
        };
      case 'top':
        return {
          position: 'fixed',
          top: Math.max(20, targetRect.top - tooltipH - pad),
          left: Math.max(20, Math.min(targetRect.centerX - tooltipW / 2, window.innerWidth - tooltipW - 20)),
        };
      case 'right':
        return {
          position: 'fixed',
          top: Math.max(20, Math.min(targetRect.centerY - tooltipH / 2, window.innerHeight - tooltipH - 20)),
          left: Math.min(targetRect.left + targetRect.width + pad, window.innerWidth - tooltipW - 20),
        };
      case 'left':
        return {
          position: 'fixed',
          top: Math.max(20, Math.min(targetRect.centerY - tooltipH / 2, window.innerHeight - tooltipH - 20)),
          left: Math.max(20, targetRect.left - tooltipW - pad),
        };
      default:
        return {
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
        };
    }
  };

  return (
    <div className="fixed inset-0 z-[9999]" style={{ pointerEvents: 'auto' }}>
      {/* ── Dark overlay with spotlight cutout ───────────── */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.4 }}
        className="absolute inset-0"
        onClick={(e) => e.stopPropagation()}
      >
        <svg width="100%" height="100%" className="absolute inset-0">
          <defs>
            <mask id="spotlight-mask">
              <rect width="100%" height="100%" fill="white" />
              {targetRect && (
                <motion.rect
                  initial={{ opacity: 0 }}
                  animate={{
                    x: targetRect.left - 8,
                    y: targetRect.top - 8,
                    width: targetRect.width + 16,
                    height: targetRect.height + 16,
                    opacity: 1,
                    rx: 12,
                    ry: 12,
                  }}
                  transition={{ duration: 0.4, ease }}
                  fill="black"
                />
              )}
            </mask>

            {/* Glow filter for the spotlight ring */}
            <filter id="spotlight-glow">
              <feGaussianBlur stdDeviation="8" result="blur" />
              <feFlood floodColor="#6366f1" floodOpacity="0.6" result="color" />
              <feComposite in="color" in2="blur" operator="in" result="glow" />
              <feMerge>
                <feMergeNode in="glow" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Dark backdrop with mask cutout */}
          <rect
            width="100%"
            height="100%"
            fill="rgba(0, 0, 0, 0.75)"
            mask="url(#spotlight-mask)"
          />

          {/* Glowing ring around the spotlight area */}
          {targetRect && (
            <motion.rect
              initial={{ opacity: 0 }}
              animate={{
                x: targetRect.left - 10,
                y: targetRect.top - 10,
                width: targetRect.width + 20,
                height: targetRect.height + 20,
                opacity: 1,
              }}
              transition={{ duration: 0.4, ease }}
              rx="14"
              ry="14"
              fill="none"
              stroke="#6366f1"
              strokeWidth="2"
              filter="url(#spotlight-glow)"
              className="animate-pulse"
            />
          )}
        </svg>
      </motion.div>

      {/* ── Animated pointer ─────────────────────────────── */}
      <AnimatePresence>
        {targetRect && (
          <motion.div
            key={`pointer-${currentStep}`}
            initial={{ opacity: 0, scale: 0.5, x: targetRect.centerX - 12, y: targetRect.centerY - 12 }}
            animate={{
              opacity: [0, 1, 1, 0.7, 1],
              scale: [0.5, 1.1, 1, 0.9, 1],
              x: targetRect.centerX - 12,
              y: targetRect.centerY - 12,
            }}
            exit={{ opacity: 0, scale: 0.5 }}
            transition={{ duration: 1.5, ease, repeat: Infinity, repeatDelay: 1 }}
            className="fixed z-[10001] pointer-events-none"
          >
            <MousePointerClick size={24} className="text-brand-400 drop-shadow-[0_0_8px_rgba(99,102,241,0.6)]" />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Tooltip card ─────────────────────────────────── */}
      <AnimatePresence mode="wait">
        <motion.div
          key={currentStep}
          initial={{ opacity: 0, y: 16, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -12, scale: 0.95 }}
          transition={{ duration: 0.35, ease }}
          style={getTooltipStyle()}
          className="z-[10002] w-[380px] max-w-[calc(100vw-40px)]"
        >
          <div className="bg-surface-100 border border-surface-300/70 rounded-2xl shadow-soft-lg overflow-hidden">
            {/* Progress bar */}
            <div className="h-1 bg-surface-300/50">
              <motion.div
                className="h-full gradient-brand rounded-r-full"
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.5, ease }}
              />
            </div>

            <div className="p-6">
              {/* Step icon & counter */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  {step.icon && (
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500/20 to-brand-600/10 flex items-center justify-center">
                      <step.icon size={20} className="text-brand-400" />
                    </div>
                  )}
                  <span className="text-xs font-medium text-surface-600 uppercase tracking-wider">
                    Step {currentStep + 1} of {totalSteps}
                  </span>
                </div>
                <button
                  onClick={onComplete}
                  className="p-1.5 rounded-lg text-surface-600 hover:text-surface-800 hover:bg-surface-200/80 transition-all"
                  title="Skip tutorial"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Title & description */}
              <h3 className="text-lg font-semibold text-white mb-2">{step.title}</h3>
              <p className="text-sm text-surface-700 leading-relaxed mb-6">{step.description}</p>

              {/* Navigation buttons */}
              <div className="flex items-center justify-between">
                <button
                  onClick={onComplete}
                  className="text-xs text-surface-600 hover:text-surface-800 transition-colors"
                >
                  Skip Tutorial
                </button>

                <div className="flex items-center gap-2">
                  {currentStep > 0 && (
                    <motion.button
                      whileHover={{ scale: 1.04 }}
                      whileTap={{ scale: 0.96 }}
                      onClick={goPrev}
                      className="flex items-center gap-1 px-4 py-2 rounded-xl text-sm font-medium text-surface-700 bg-surface-200/80 border border-surface-300 hover:bg-surface-300/80 transition-all"
                    >
                      <ChevronLeft size={14} />
                      Back
                    </motion.button>
                  )}
                  <motion.button
                    whileHover={{ scale: 1.04, y: -1 }}
                    whileTap={{ scale: 0.96 }}
                    onClick={goNext}
                    className="btn-primary flex items-center gap-1.5 px-5 py-2"
                  >
                    {currentStep === totalSteps - 1 ? (
                      <>
                        Get Started
                        <Sparkles size={14} />
                      </>
                    ) : (
                      <>
                        Next
                        <ChevronRight size={14} />
                      </>
                    )}
                  </motion.button>
                </div>
              </div>

              {/* Step dots */}
              <div className="flex items-center justify-center gap-1.5 mt-5">
                {STEPS.map((_, i) => (
                  <motion.div
                    key={i}
                    className={`rounded-full transition-all duration-300 ${
                      i === currentStep
                        ? 'w-6 h-1.5 gradient-brand'
                        : i < currentStep
                        ? 'w-1.5 h-1.5 bg-brand-500/50'
                        : 'w-1.5 h-1.5 bg-surface-400'
                    }`}
                    layout
                  />
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
