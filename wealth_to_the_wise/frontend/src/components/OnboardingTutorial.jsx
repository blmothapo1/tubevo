/**
 * Interactive Adobe-style guided onboarding tutorial.
 *
 * Shows a spotlight overlay that walks new users through the UI
 * step by step, highlighting elements with a glow/focus effect,
 * darkening the rest of the screen, and displaying tooltip
 * instructions with an animated pointer.
 *
 * Enhanced with:
 * - useDeviceContext-based layout (mobile / tablet / desktop presets)
 * - Collision detection (auto-flip tooltip if offscreen)
 * - Mobile bottom-sheet modal fallback
 * - Tablet anchored tooltips with safe padding
 * - Desktop anchored tooltips with arrows near target
 * - 16px minimum edge padding on ALL device types
 * - Orientation change + visualViewport listener
 * - Scroll-into-view for off-screen targets
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
import useDeviceContext from '../hooks/useDeviceContext';

const ease = [0.25, 0.1, 0.25, 1];

// ── Layout presets per device ────────────────────────────────
// Minimum padding from any screen edge (px)
const EDGE_PAD = {
  mobile: 16,
  tablet: 16,
  desktop: 20,
};
// Tooltip width (px)
const TOOLTIP_W = {
  mobile: 0,     // full-width bottom sheet on mobile — not used for positioning
  tablet: 340,
  desktop: 380,
};
// Estimated tooltip height for collision math
const TOOLTIP_H = {
  mobile: 0,
  tablet: 220,
  desktop: 240,
};

// ── Tutorial step definitions ────────────────────────────────
// Each step can have an optional `mobileDescription` for small screens.
const STEPS = [
  {
    id: 'welcome',
    title: 'Welcome to Tubevo! 🎬',
    description:
      'Let\'s take a quick tour to get you set up. We\'ll walk through adding your API keys, generating your first video, and more.',
    mobileDescription:
      'Quick tour! We\'ll help you add API keys and generate your first video.',
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
    mobileDescription:
      'Tap the ☰ menu button to open navigation. Access Dashboard, Videos, Schedule, and Settings.',
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
    mobileDescription:
      'Go to Settings → API Keys to paste your OpenAI, ElevenLabs, and Pexels keys.',
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
    mobileDescription:
      'Tap Generate to start the pipeline: script → voice → footage → video (~2–3 min).',
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

  // ── Device context (robust detection) ─────────────────────
  const device = useDeviceContext();

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
        // Scroll target into view if it's off-screen
        const elRect = el.getBoundingClientRect();
        const vw = device.width;
        const vh = device.height;
        const isOffScreen =
          elRect.bottom < 0 ||
          elRect.top > vh ||
          elRect.right < 0 ||
          elRect.left > vw;

        if (isOffScreen) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
          // Re-read rect after scroll
          setTimeout(() => {
            const rect = el.getBoundingClientRect();
            setTargetRect({
              top: rect.top,
              left: rect.left,
              width: rect.width,
              height: rect.height,
              centerX: rect.left + rect.width / 2,
              centerY: rect.top + rect.height / 2,
            });
          }, 400);
          return;
        }

        setTargetRect({
          top: elRect.top,
          left: elRect.left,
          width: elRect.width,
          height: elRect.height,
          centerX: elRect.left + elRect.width / 2,
          centerY: elRect.top + elRect.height / 2,
        });
      } else {
        setTargetRect(null);
      }
    }, 400);

    return () => clearTimeout(timer);
  }, [step.target, device.width, device.height]);

  // Navigate to the step's route if needed
  useEffect(() => {
    if (step.route) {
      const [path] = step.route.split('?');
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

    const handleUpdate = () => updateTargetRect();
    window.addEventListener('resize', handleUpdate);
    window.addEventListener('scroll', handleUpdate, true);
    window.addEventListener('orientationchange', handleUpdate);

    // visualViewport for accurate mobile sizing
    const vv = window.visualViewport;
    if (vv) vv.addEventListener('resize', handleUpdate);

    return () => {
      if (cleanup) cleanup();
      window.removeEventListener('resize', handleUpdate);
      window.removeEventListener('scroll', handleUpdate, true);
      window.removeEventListener('orientationchange', handleUpdate);
      if (vv) vv.removeEventListener('resize', handleUpdate);
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

  // ── Compute tooltip position with collision detection ─────
  const getTooltipStyle = () => {
    const { deviceType } = device;
    const pad = EDGE_PAD[deviceType];

    // Mobile: ALWAYS use bottom-sheet modal (no anchored positioning)
    if (deviceType === 'mobile') {
      return null; // Signals mobile bottom-sheet
    }

    // Center steps (no target) — centered modal for all devices
    if (step.position === 'center' || !targetRect) {
      return {
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
      };
    }

    const tooltipW = TOOLTIP_W[deviceType];
    const tooltipH = TOOLTIP_H[deviceType];
    const vw = device.width;
    const vh = device.height;

    // Determine best position with collision detection
    let preferredPos = step.position;

    // Check if preferred position overflows; if so, flip
    const wouldOverflow = (pos) => {
      switch (pos) {
        case 'bottom': return targetRect.top + targetRect.height + pad + tooltipH > vh - pad;
        case 'top':    return targetRect.top - tooltipH - pad < pad;
        case 'right':  return targetRect.left + targetRect.width + pad + tooltipW > vw - pad;
        case 'left':   return targetRect.left - tooltipW - pad < pad;
        default: return false;
      }
    };

    if (wouldOverflow(preferredPos)) {
      // Flip to opposite
      const flip = { bottom: 'top', top: 'bottom', right: 'left', left: 'right' };
      preferredPos = flip[preferredPos] || preferredPos;
    }

    // If still overflowing after flip, try all positions
    if (wouldOverflow(preferredPos)) {
      const candidates = ['bottom', 'top', 'right', 'left'];
      preferredPos = candidates.find((p) => !wouldOverflow(p)) || 'bottom';
    }

    // Clamp helper — ensures >= pad from all edges
    const clampX = (x) => Math.max(pad, Math.min(x, vw - tooltipW - pad));
    const clampY = (y) => Math.max(pad, Math.min(y, vh - tooltipH - pad));

    switch (preferredPos) {
      case 'bottom':
        return {
          position: 'fixed',
          top: clampY(targetRect.top + targetRect.height + pad),
          left: clampX(targetRect.centerX - tooltipW / 2),
        };
      case 'top':
        return {
          position: 'fixed',
          top: clampY(targetRect.top - tooltipH - pad),
          left: clampX(targetRect.centerX - tooltipW / 2),
        };
      case 'right':
        return {
          position: 'fixed',
          top: clampY(targetRect.centerY - tooltipH / 2),
          left: clampX(targetRect.left + targetRect.width + pad),
        };
      case 'left':
        return {
          position: 'fixed',
          top: clampY(targetRect.centerY - tooltipH / 2),
          left: clampX(targetRect.left - tooltipW - pad),
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

  // Get device-aware description text
  const getDescription = () => {
    if (device.isMobile && step.mobileDescription) return step.mobileDescription;
    return step.description;
  };

  // ── Tooltip width class per device ─────────────────────────
  const tooltipWidthClass = device.isTablet
    ? 'w-[340px] max-w-[calc(100vw-32px)]'
    : 'w-[380px] max-w-[calc(100vw-40px)]';

  // ── Shared tooltip card content (used in both positioned + modal) ──
  const renderTooltipContent = () => (
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

      <div className={device.isMobile ? 'p-4' : 'p-5 sm:p-6'}>
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
        <h3 className={`font-semibold text-white mb-2 ${device.isMobile ? 'text-base' : 'text-lg'}`}>
          {step.title}
        </h3>
        <p className={`text-surface-700 leading-relaxed mb-5 ${device.isMobile ? 'text-xs' : 'text-sm'}`}>
          {getDescription()}
        </p>

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
  );

  const tooltipStyle = getTooltipStyle();
  const useMobileModal = tooltipStyle === null;

  // Spotlight cutout padding (smaller on mobile to avoid tight edges)
  const spotlightPad = device.isMobile ? 6 : 8;
  const spotlightBorderPad = device.isMobile ? 8 : 10;

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
                    x: targetRect.left - spotlightPad,
                    y: targetRect.top - spotlightPad,
                    width: targetRect.width + spotlightPad * 2,
                    height: targetRect.height + spotlightPad * 2,
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
                x: targetRect.left - spotlightBorderPad,
                y: targetRect.top - spotlightBorderPad,
                width: targetRect.width + spotlightBorderPad * 2,
                height: targetRect.height + spotlightBorderPad * 2,
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

      {/* ── Animated pointer (hidden on mobile modal) ────── */}
      <AnimatePresence>
        {targetRect && !useMobileModal && (
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

      {/* ── Tooltip card — mobile bottom-sheet / tablet+desktop anchored ─ */}
      <AnimatePresence mode="wait">
        {useMobileModal ? (
          /* ── Mobile bottom-sheet modal ─────────────────── */
          <motion.div
            key={`mobile-${currentStep}`}
            initial={{ opacity: 0, y: 100 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 100 }}
            transition={{ duration: 0.35, ease }}
            className="onboarding-mobile-modal"
          >
            <div className="onboarding-card">
              {renderTooltipContent()}
            </div>
          </motion.div>
        ) : (
          /* ── Tablet / Desktop positioned tooltip ──────── */
          <motion.div
            key={currentStep}
            initial={{ opacity: 0, y: 16, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -12, scale: 0.95 }}
            transition={{ duration: 0.35, ease }}
            className={`z-[10002] ${tooltipWidthClass}`}
            style={tooltipStyle}
          >
            {renderTooltipContent()}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
