// filepath: frontend/src/hooks/useOnboarding.js
/**
 * Custom hook to manage the onboarding tutorial state.
 *
 * Uses localStorage to persist `hasCompletedOnboarding` —
 * false for new users (triggers auto-show), true after completion/skip.
 *
 * A custom event (`onboarding-changed`) keeps multiple hook instances
 * in sync (e.g. Settings "Replay" button triggers DashboardLayout overlay).
 *
 * 100% additive — does not modify any existing logic.
 */
import { useState, useCallback, useEffect } from 'react';

const STORAGE_KEY = 'hasCompletedOnboarding';
const SYNC_EVENT = 'onboarding-changed';

function readFlag() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

export default function useOnboarding() {
  const [hasCompleted, setHasCompleted] = useState(readFlag);
  const [forceShow, setForceShow] = useState(false);

  // Listen for cross-instance sync events
  useEffect(() => {
    const handler = (e) => {
      const completed = e.detail?.completed ?? readFlag();
      setHasCompleted(completed);
      if (!completed) setForceShow(true);
    };
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, []);

  const showTutorial = !hasCompleted || forceShow;

  const completeTutorial = useCallback(() => {
    try { localStorage.setItem(STORAGE_KEY, 'true'); } catch { /* silent */ }
    setHasCompleted(true);
    setForceShow(false);
    window.dispatchEvent(new CustomEvent(SYNC_EVENT, { detail: { completed: true } }));
  }, []);

  const replayTutorial = useCallback(() => {
    try { localStorage.setItem(STORAGE_KEY, 'false'); } catch { /* silent */ }
    setHasCompleted(false);
    setForceShow(true);
    window.dispatchEvent(new CustomEvent(SYNC_EVENT, { detail: { completed: false } }));
  }, []);

  return { showTutorial, completeTutorial, replayTutorial };
}
