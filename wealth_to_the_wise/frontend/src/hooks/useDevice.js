/**
 * useDevice — responsive device detection hook with optional debug overlay.
 *
 * Returns: { isMobile, isTablet, isDesktop, deviceType, width, height, isLandscape }
 *
 * Usage:
 *   const { isMobile, isTablet, isDesktop } = useDevice();
 *
 * The debug overlay renders automatically in dev mode when ?debug=device
 * is present in the URL. Fully additive — no side-effects on existing logic.
 */
import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

const BREAKPOINTS = { mobile: 640, tablet: 1024 };

function getDeviceInfo() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  const isMobile = w < BREAKPOINTS.mobile;
  const isTablet = w >= BREAKPOINTS.mobile && w < BREAKPOINTS.tablet;
  const isDesktop = w >= BREAKPOINTS.tablet;
  const deviceType = isMobile ? 'mobile' : isTablet ? 'tablet' : 'desktop';
  const isLandscape = w > h;

  return { isMobile, isTablet, isDesktop, deviceType, width: w, height: h, isLandscape };
}

export default function useDevice() {
  const [device, setDevice] = useState(getDeviceInfo);

  const handleChange = useCallback(() => {
    setDevice(getDeviceInfo());
  }, []);

  useEffect(() => {
    window.addEventListener('resize', handleChange);
    window.addEventListener('orientationchange', handleChange);
    // Also use matchMedia for more reliable detection
    const mql = window.matchMedia(`(max-width: ${BREAKPOINTS.mobile - 1}px)`);
    const mqlTablet = window.matchMedia(`(max-width: ${BREAKPOINTS.tablet - 1}px)`);
    mql.addEventListener?.('change', handleChange);
    mqlTablet.addEventListener?.('change', handleChange);

    return () => {
      window.removeEventListener('resize', handleChange);
      window.removeEventListener('orientationchange', handleChange);
      mql.removeEventListener?.('change', handleChange);
      mqlTablet.removeEventListener?.('change', handleChange);
    };
  }, [handleChange]);

  return device;
}

/**
 * DeviceDebugOverlay — portal-based debug badge.
 * Renders only in development when ?debug=device is in the URL.
 *
 * Usage: <DeviceDebugOverlay /> anywhere in the tree.
 */
export function DeviceDebugOverlay() {
  const device = useDevice();
  const [show, setShow] = useState(false);

  useEffect(() => {
    const isDev = import.meta.env.DEV;
    const hasFlag = new URLSearchParams(window.location.search).get('debug') === 'device';
    setShow(isDev && hasFlag);
  }, []);

  if (!show) return null;

  const badge = (
    <div
      style={{
        position: 'fixed',
        bottom: 8,
        left: 8,
        zIndex: 99999,
        padding: '6px 12px',
        borderRadius: 10,
        fontSize: 11,
        fontFamily: 'monospace',
        background: 'rgba(0,0,0,0.85)',
        color: '#a5f3fc',
        border: '1px solid rgba(99,102,241,0.3)',
        backdropFilter: 'blur(8px)',
        pointerEvents: 'none',
        lineHeight: 1.5,
      }}
    >
      <div><strong>{device.deviceType.toUpperCase()}</strong></div>
      <div>{device.width}×{device.height} {device.isLandscape ? '⬌' : '⬍'}</div>
    </div>
  );

  return createPortal(badge, document.body);
}
