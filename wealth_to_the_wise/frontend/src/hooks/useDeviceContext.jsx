/**
 * useDeviceContext — robust device detection hook.
 *
 * Uses CSS media queries (pointer, hover) combined with viewport size
 * to reliably classify devices. iPadOS reports "desktop" UA, so we
 * never rely on UA alone — pointer/hover queries take priority.
 *
 * Returns:
 *   deviceType:   "mobile" | "tablet" | "desktop"
 *   inputType:    "touch" | "mouse"
 *   orientation:  "portrait" | "landscape"
 *   width:        number  (visual viewport width)
 *   height:       number  (visual viewport height)
 *   isMobile:     boolean
 *   isTablet:     boolean
 *   isDesktop:    boolean
 *
 * Recomputes on: resize, orientationchange, visualViewport resize,
 * and matchMedia changes. Debounced at 100ms to avoid re-render loops.
 */
import { useState, useEffect, useCallback, useRef } from 'react';

// ── Media query matchers (created once) ──────────────────────
const MQ = {
  pointerCoarse: '(pointer: coarse)',
  pointerFine:   '(pointer: fine)',
  hoverNone:     '(hover: none)',
  hoverHover:    '(hover: hover)',
  anyPointerFine:'(any-pointer: fine)',
};

// ── Viewport helpers ─────────────────────────────────────────
function getViewport() {
  // Prefer visualViewport for accurate mobile sizing (accounts for
  // on-screen keyboard, pinch zoom, etc.)
  const vv = window.visualViewport;
  if (vv) {
    return { width: Math.round(vv.width), height: Math.round(vv.height) };
  }
  return { width: window.innerWidth, height: window.innerHeight };
}

function mqMatches(query) {
  try { return window.matchMedia(query).matches; } catch { return false; }
}

// ── Core detection logic ─────────────────────────────────────
function detect() {
  const { width, height } = getViewport();

  // Input capability detection via media queries
  const pointerCoarse = mqMatches(MQ.pointerCoarse);
  const pointerFine   = mqMatches(MQ.pointerFine);
  const hoverNone     = mqMatches(MQ.hoverNone);
  const hoverHover    = mqMatches(MQ.hoverHover);
  const anyPointerFine= mqMatches(MQ.anyPointerFine);

  // Touch capability (media query based — more reliable than navigator.maxTouchPoints for classification)
  const isLikelyTouch = pointerCoarse || hoverNone;
  const isLikelyMouse = pointerFine && hoverHover;

  // inputType
  const inputType = isLikelyTouch && !isLikelyMouse ? 'touch' : 'mouse';

  // deviceType — combine input method WITH viewport width
  let deviceType = 'desktop';

  if (width < 768 && isLikelyTouch) {
    // Small screen + touch = definitely mobile
    deviceType = 'mobile';
  } else if (width < 768 && !isLikelyTouch) {
    // Small window on desktop (resized browser) — still treat as mobile layout
    deviceType = 'mobile';
  } else if (width >= 768 && width < 1024 && isLikelyTouch) {
    // Medium screen + touch = tablet (iPad, Android tablet)
    deviceType = 'tablet';
  } else if (width >= 768 && width < 1024 && !isLikelyTouch) {
    // Medium window on desktop — treat as tablet layout for responsiveness
    deviceType = 'tablet';
  } else if (width >= 1024 && isLikelyTouch && !anyPointerFine) {
    // Large screen but only coarse pointer (e.g. iPadOS 13+ in landscape,
    // large Android tablets). iPadOS lies about UA but pointer: coarse is truthful.
    deviceType = 'tablet';
  } else {
    // width >= 1024 AND (mouse/trackpad available) => desktop
    deviceType = 'desktop';
  }

  const orientation = width >= height ? 'landscape' : 'portrait';

  // Dev-mode logging
  if (import.meta.env.DEV) {
    console.log('[DeviceContext]', {
      deviceType,
      inputType,
      width,
      height,
      orientation,
      pointer: pointerCoarse ? 'coarse' : pointerFine ? 'fine' : 'unknown',
      hover: hoverHover ? 'hover' : hoverNone ? 'none' : 'unknown',
    });
  }

  return {
    deviceType,
    inputType,
    orientation,
    width,
    height,
    isMobile:  deviceType === 'mobile',
    isTablet:  deviceType === 'tablet',
    isDesktop: deviceType === 'desktop',
  };
}

// ── Hook ─────────────────────────────────────────────────────
export default function useDeviceContext() {
  const [ctx, setCtx] = useState(detect);
  const timerRef = useRef(null);

  // Debounced updater — 100ms to avoid render storms during resize drag
  const update = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setCtx((prev) => {
        const next = detect();
        // Only trigger re-render if something actually changed
        if (
          prev.deviceType === next.deviceType &&
          prev.inputType  === next.inputType &&
          prev.orientation=== next.orientation &&
          prev.width      === next.width &&
          prev.height     === next.height
        ) {
          return prev; // same reference → no re-render
        }
        return next;
      });
    }, 100);
  }, []);

  useEffect(() => {
    // Standard listeners
    window.addEventListener('resize', update);
    window.addEventListener('orientationchange', update);

    // visualViewport resize (more accurate on mobile)
    const vv = window.visualViewport;
    if (vv) {
      vv.addEventListener('resize', update);
      vv.addEventListener('scroll', update);
    }

    // matchMedia change listeners (fires instantly on connect/disconnect of mouse, etc.)
    const mqls = Object.values(MQ).map((q) => {
      try {
        const mql = window.matchMedia(q);
        mql.addEventListener('change', update);
        return mql;
      } catch { return null; }
    });

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      window.removeEventListener('resize', update);
      window.removeEventListener('orientationchange', update);
      if (vv) {
        vv.removeEventListener('resize', update);
        vv.removeEventListener('scroll', update);
      }
      mqls.forEach((mql) => mql?.removeEventListener?.('change', update));
    };
  }, [update]);

  return ctx;
}
