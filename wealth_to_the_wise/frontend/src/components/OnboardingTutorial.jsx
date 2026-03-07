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
      'Let\'s take a quick tour to get you set up. We\'ll walk through adding your API keys, creating your first video, and more.',
    mobileDescription:
      'Quick tour! We\'ll help you add API keys and create your first video.',
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
      'Head to Settings → API Keys to paste your OpenAI, ElevenLabs, and Pexels keys. These power your scripts, voiceovers, and footage.',
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
      'Type any topic you want a video about — e.g. "5 Habits of Wealthy People". Tubevo writes the script for you.',
    icon: Wand2,
    target: '[data-tour="topic-input"]',
    route: '/videos',
    position: 'bottom',
    duration: 10000,
  },
  {
    id: 'generate-button',
    title: 'Click Create',
    description:
      'Hit the Create button to kick off the full pipeline: script → voiceover → stock footage → video. It takes about 2–3 minutes.',
    mobileDescription:
      'Tap Create to start the pipeline: script → voice → footage → video (~2–3 min).',
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
    <div className="bg-surface-100 surface-modal overflow-hidden">
      {/* Progress bar */}
      <div className="h-[3px] bg-surface-300/50">
        <motion.div
          className="h-full bg-brand-500 rounded-r-full"
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.4, ease }}
        />
      </div>

      <div className={device.isMobile ? 'p-4' : 'p-5 sm:p-6'}>
        {/* Step icon & counter */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2.5">
            {step.icon && (
              <div className="w-9 h-9 rounded-[10px] bg-brand-500/10 flex items-center justify-center">
                <step.icon size={16} className="text-brand-400" />
              </div>
            )}
            <span className="text-[11px] font-semibold text-surface-500 uppercase tracking-[0.08em] tabular-nums">
              {String(currentStep + 1).padStart(2, '0')} / {String(totalSteps).padStart(2, '0')}
            </span>
          </div>
          <button
            onClick={onComplete}
            className="p-1 rounded-[6px] text-surface-600 hover:text-surface-800 hover:bg-surface-200/80 transition-colors"
            title="Skip tutorial"
          >
            <X size={14} />
          </button>
        </div>

        {/* Title & description */}
        <h3 className={`font-semibold text-white mb-1.5 ${device.isMobile ? 'text-[14px]' : 'text-[15px]'}`}>
          {step.title}
        </h3>
        <p className={`text-surface-700 leading-relaxed mb-4 ${device.isMobile ? 'text-[12px]' : 'text-[13px]'}`}>
          {getDescription()}
        </p>

        {/* Navigation buttons */}
        <div className="flex items-center justify-between">
          <button
            onClick={onComplete}
            className="text-[12px] text-surface-600 hover:text-surface-800 transition-colors"
          >
            Skip Tutorial
          </button>

          <div className="flex items-center gap-2">
            {currentStep > 0 && (
              <motion.button
                whileTap={{ scale: 0.97 }}
                onClick={goPrev}
                className="flex items-center gap-1 px-3 py-1.5 rounded-[8px] text-[13px] font-medium text-surface-700 bg-surface-200/80 hover:bg-surface-300/80 transition-colors"
              >
                <ChevronLeft size={14} />
                Back
              </motion.button>
            )}
            <motion.button
              whileTap={{ scale: 0.97 }}
              onClick={goNext}
              className="btn-primary flex items-center gap-1.5 px-4 py-1.5 text-[13px]"
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

        {/* Step dots — 8px circles */}
        <div className="flex items-center justify-center gap-1.5 mt-4">
          {STEPS.map((_, i) => (
            <motion.div
              key={i}
              className={`w-[8px] h-[8px] rounded-full transition-all duration-200 ${
                i === currentStep
                  ? 'bg-brand-500 scale-110'
                  : i < currentStep
                  ? 'bg-brand-500/50'
                  : 'bg-surface-400'
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
                    rx: 10,
                    ry: 10,
                  }}
                  transition={{ duration: 0.4, ease }}
                  fill="black"
                />
              )}
            </mask>

            {/* Soft halo filter for the spotlight ring */}
            <filter id="spotlight-glow">
              <feGaussianBlur stdDeviation="8" result="blur" />
              <feFlood floodColor="#2563eb" floodOpacity="0.15" result="color" />
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
              rx="10"
              ry="10"
              fill="none"
              stroke="#2563eb"
              strokeWidth="0.5"
              strokeOpacity="0.4"
              filter="url(#spotlight-glow)"
              className="animate-halo-pulse"
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
            <MousePointerClick size={24} className="text-brand-400 drop-shadow-[0_0_6px_rgba(37,99,235,0.5)]" />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Tooltip card — mobile bottom-sheet / tablet+desktop anchored ─ */}
      <AnimatePresence mode="wait">
        {useMobileModal ? (
          /* ── Mobile bottom-sheet modal ─────────────────── */
          <motion.div
            key={`mobile-${currentStep}`}
            initial={{ opacity: 0, y: 80 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 80 }}
            transition={{ duration: 0.25, ease }}
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
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2, ease }}
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
