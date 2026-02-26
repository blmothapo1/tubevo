/**
 * useDevice — backward-compatible device detection hook.
 *
 * Now delegates to useDeviceContext() for accurate media-query-based
 * detection (pointer, hover, visualViewport). The returned shape is
 * a superset of the original API so nothing breaks.
 *
 * Also exports DeviceDebugOverlay with richer context display.
 */
import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import useDeviceContext from './useDeviceContext';

export default function useDevice() {
  // Delegate to the robust context hook — returns everything the old
  // hook did plus inputType, orientation, etc.
  return useDeviceContext();
}

/**
 * DeviceDebugOverlay — portal-based debug badge.
 * Renders only in development when ?debug=device is in the URL.
 *
 * Usage: <DeviceDebugOverlay /> anywhere in the tree.
 */
export function DeviceDebugOverlay() {
  const device = useDeviceContext();
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
      <div><strong>{device.deviceType.toUpperCase()}</strong> · {device.inputType}</div>
      <div>{device.width}×{device.height} {device.orientation === 'landscape' ? '⬌' : '⬍'}</div>
    </div>
  );

  return createPortal(badge, document.body);
}
