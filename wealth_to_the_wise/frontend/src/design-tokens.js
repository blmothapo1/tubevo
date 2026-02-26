/**
 * Tubevo Design Tokens — "Apple × Tesla" Polish System
 *
 * Surface hierarchy:
 *   base   → the app background (near-black, slightly warm)
 *   s1     → main canvas panels (sidebar, main content area)
 *   s2     → cards / modules that "float" above the canvas
 *   s3     → popovers, tooltips, modals (strongest elevation)
 *
 * Separation via:
 *   1. surface color delta between layers
 *   2. rgba borders (no hard dividers)
 *   3. spacing (4px base grid)
 *   4. corner radius (16px cards, 10px inputs, 6px small elements)
 */

// ── Color Palette ───────────────────────────────────────
export const colors = {
  brand: {
    50:  '#eef4ff',
    100: '#d9e6ff',
    200: '#b3ccff',
    300: '#6e9cff',
    400: '#3b82f6',
    500: '#2563eb',
    600: '#1d4ed8',
    700: '#1e40af',
  },

  // Surface layers — warm charcoal, NOT cool/navy
  base:   '#09090b',   // app background (zinc-950)
  s1:     '#111113',   // main canvas / sidebar fill
  s2:     '#18181b',   // cards / floating modules (zinc-900)
  s3:     '#27272a',   // popovers / modals / tooltips (zinc-800)
  well:   '#0c0c0e',   // inset wells (inputs sit here)

  // Neutral scale for text + muted UI
  neutral: {
    100: '#f4f4f5',  // primary text (zinc-100)
    200: '#e4e4e7',  // secondary text (zinc-200)
    300: '#d4d4d8',  // muted text (zinc-300)
    400: '#a1a1aa',  // placeholder / micro-labels (zinc-400)
    500: '#71717a',  // disabled text (zinc-500)
    600: '#52525b',  // ghost elements (zinc-600)
    700: '#3f3f46',  // subtle line (zinc-700) — ultra-low opacity only
    800: '#27272a',  // bg elements
  },

  // Semantic
  success: '#34d399',
  warning: '#fbbf24',
  error:   '#f87171',
};

// ── Spacing (8pt grid) ──────────────────────────────────
export const spacing = {
  0:  '0px',
  1:  '4px',
  2:  '8px',
  3:  '12px',
  4:  '16px',
  5:  '20px',
  6:  '24px',
  8:  '32px',
  10: '40px',
  12: '48px',
  16: '64px',
};

// ── Radius ──────────────────────────────────────────────
export const radius = {
  sm:   '6px',   // small elements, badges
  md:   '10px',  // inputs, inner elements
  lg:   '16px',  // cards, panels (primary)
  xl:   '20px',  // modals, overlays
  full: '9999px',// pills, avatars
};

// ── Elevation (shadow layers) ───────────────────────────
export const elevation = {
  none: 'none',
  s1: '0 1px 2px rgba(0,0,0,0.2)',                              // canvas panels
  s2: '0 2px 8px rgba(0,0,0,0.25), 0 0 1px rgba(0,0,0,0.1)',   // cards
  s3: '0 8px 32px rgba(0,0,0,0.45), 0 0 1px rgba(0,0,0,0.15)', // modals/tooltips
};

// ── Typography ──────────────────────────────────────────
export const fonts = {
  sans:  '-apple-system, "SF Pro Display", "Helvetica Neue", system-ui, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  mono:  '"SF Mono", "Fira Code", "JetBrains Mono", "Cascadia Code", ui-monospace, monospace',
};

export const text = {
  micro:   { size: '10px',  weight: 600, tracking: '0.08em', transform: 'uppercase' },
  caption: { size: '11px',  weight: 500, tracking: '0.02em' },
  body:    { size: '14px',  weight: 400, tracking: '-0.003em' },
  label:   { size: '12px',  weight: 500, tracking: '0.01em' },
  heading: { size: '20px',  weight: 600, tracking: '-0.02em' },
  display: { size: '32px',  weight: 700, tracking: '-0.03em' },
};

// ── Transitions ─────────────────────────────────────────
export const motion = {
  fast:    '0.12s ease',
  normal:  '0.2s ease',
  smooth:  '0.35s cubic-bezier(0.25, 0.1, 0.25, 1)',
};

export default {
  colors,
  spacing,
  radius,
  elevation,
  fonts,
  text,
  motion,
};
