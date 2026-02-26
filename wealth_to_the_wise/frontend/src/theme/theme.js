/**
 * Theme Module — System Theme Sync
 * 3-option: 'system' (default) | 'dark' | 'light'
 * Persists to localStorage, applies via data-theme attribute on <html>.
 */

const STORAGE_KEY = 'tubevo-theme-preference';

/** Detect OS preference */
export function getSystemTheme() {
  if (typeof window === 'undefined') return 'dark';
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

/** Read stored preference (or 'system' default) */
export function getStoredPreference() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === 'dark' || v === 'light' || v === 'system') return v;
  } catch { /* SSR / private browsing */ }
  return 'system';
}

/** Resolve the effective theme from a preference string */
function resolveTheme(pref) {
  if (pref === 'dark' || pref === 'light') return pref;
  return getSystemTheme();
}

/** Set data-theme on <html> */
export function applyTheme(pref) {
  const theme = resolveTheme(pref ?? getStoredPreference());
  document.documentElement.setAttribute('data-theme', theme);
  return theme;
}

/** Persist preference and apply */
export function setPreference(pref) {
  try { localStorage.setItem(STORAGE_KEY, pref); } catch { /* ignore */ }
  applyTheme(pref);
}

/** Boot-time init + OS listener (returns cleanup fn) */
export function initTheme() {
  const pref = getStoredPreference();
  applyTheme(pref);

  const mql = window.matchMedia('(prefers-color-scheme: light)');
  function onChange() {
    // Only react if user chose "system"
    if (getStoredPreference() === 'system') applyTheme('system');
  }
  mql.addEventListener('change', onChange);
  return () => mql.removeEventListener('change', onChange);
}
